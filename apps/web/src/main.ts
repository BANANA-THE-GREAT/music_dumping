import {
  JOB_STAGE_LABELS,
  type BoundarySuggestion,
  type F0Frame,
  type ProjectCatalogSummary,
  type ScoreProject as ApiScoreProject,
} from "@vocal-score/contracts";
import { ApiError, VocalScoreApi } from "@vocal-score/contracts/client";
import { ScoreHistory, type EditableNote } from "@vocal-score/score-core";
import { analyzeMusic } from "./analysis";
import { keyName, keyRootMidi } from "./key";
import {
  cleanAndQuantize,
  demoNotes,
  displayQuantizedNotes,
  mappedAbc,
} from "./music";
import { renderJianpu } from "./notation";
import { ScorePlayer } from "./playback";
import { pianoRollMetrics, renderPianoRoll } from "./piano-roll";
import { TaskProgressPanel } from "./task-progress";
import { isolateCenterVocal, resampleAudio } from "./separation";
import type { MusicalAnalysis, RawNote, ScoreNote } from "./types";
import { drawWaveform } from "./waveform";
import { VocalPreview, audioBlob } from "./vocal-preview";
import { refineLocalMelody } from "./melody";
import { detectEnergyOnsets, estimateGlobalOffset } from "./alignment";
import {
  boundaryDeltaLabel,
  boundaryReasonLabel,
  boundarySupersededLabel,
  orderedBoundarySuggestions,
  reviewableBoundarySuggestions,
} from "./boundary-review";
import "./style.css";
import "./editor.css";
import "./task-progress.css";

const KEYS = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
const api = new VocalScoreApi();
const ACTIVE_JOB_KEY = "vocal-score.active-job";
const FAILED_JOB_KEY = "vocal-score.failed-job";
document.querySelector<HTMLDivElement>("#app")!.innerHTML =
  `<main><header><div><span class="eyebrow">VOCAL SCORE STUDIO</span><h1>拾音</h1></div><p>从一首歌里分离人声，自动识别速度、拍号与调性，生成可演奏的简谱和五线谱。</p></header><section class="workbench"><aside><label class="drop" id="drop"><input id="file" type="file" accept="audio/*"><span class="drop-icon">↥</span><strong>放入歌曲或人声以创建新项目</strong><small>MP3 · WAV · OGG · FLAC</small></label><audio id="audio" controls></audio><div class="field"><label>人声分离 <output id="isolateValue">82%</output></label><input id="isolate" type="range" min="0" max="100" value="82"><small>适合主唱居中的立体声歌曲</small></div><div class="field"><label>识别灵敏度</label><select id="sensitivity"><option value="0.35">均衡</option><option value="0.48">保守</option><option value="0.25">灵敏</option></select></div><button class="primary" id="transcribe" disabled>自动分析并扒谱</button><button class="ghost" id="example">载入完整示例</button><section id="task-progress" aria-label="转录任务进度"></section><p class="status" id="status" role="status">等待音频</p></aside><article><section class="analysis-panel"><div><span>速度 BPM</span><input id="bpm" type="number" min="40" max="240" value="120"><small id="bpmConfidence">待分析</small></div><div><span>拍号</span><select id="meter"><option value="4">4 / 4</option><option value="3">3 / 4</option></select><small id="meterConfidence">待分析</small></div><div><span>调性</span><section><select id="key">${KEYS.map((k, i) => `<option value="${i}">${k}</option>`).join("")}</select><select id="mode"><option value="major">大调</option><option value="minor">小调</option></select></section><small id="keyConfidence">待分析</small></div></section><div class="toolbar"><div class="actions"><button id="play" disabled>▶ 演奏</button><button id="midi" disabled>导出 MIDI</button><button id="xml" disabled>导出 MusicXML</button></div></div><div class="score-shell"><div class="score-content"><div id="staff" class="score"></div><div id="jianpu" class="score hidden"></div><div class="empty" id="empty"><div>♪</div><strong>完整乐谱会出现在这里</strong><span>导入歌曲后，一次完成分离、分析与转谱</span></div></div><nav class="score-tools" aria-label="谱面工具"><div class="tabs"><button class="active" data-view="staff">五线谱</button><button data-view="jianpu">简谱</button></div></nav></div></article></section><footer>本地处理 · 不上传音频 · 自动识别结果可手动修正</footer></main>`;
document
  .querySelector("#midi")!
  .insertAdjacentHTML(
    "beforebegin",
    `<select id="midi-version" aria-label="MIDI 版本"><option value="score">谱面版</option><option value="performance">演唱版</option></select>`,
  );
document
  .querySelector("#play")!
  .insertAdjacentHTML(
    "beforebegin",
    `<select id="playback-version" aria-label="试听版本"><option value="score">谱面版</option><option value="performance">演唱版</option></select><select id="playback-mode" aria-label="试听音轨"><option value="mix-vocals" selected>谱面 + 人声</option><option value="score">只听谱面</option><option value="source">只听原曲</option><option value="vocals">只听人声</option><option value="mix-source">谱面 + 原曲</option></select><label class="playback-loop"><input id="playback-loop" type="checkbox">片段循环</label>`,
  );
document.querySelector(".analysis-panel")!.insertAdjacentHTML(
  "afterend",
  `<section class="tempo-map-controls" aria-label="变速设置"><div><strong>变速段</strong><small>仅影响谱面量化和导出节拍，不修改演唱版时间。</small></div><div id="tempo-map-list"></div><button id="add-tempo-point" type="button">添加变速点</button><button id="apply-tempo-map" type="button">应用变速</button><output id="tempo-map-result"></output></section>`,
);
document
  .querySelector(".score-tools")!
  .insertAdjacentHTML(
    "beforeend",
    `<div class="edit-actions"><button id="undo" title="撤销" aria-label="撤销" disabled>↶</button><button id="redo" title="重做" aria-label="重做" disabled>↷</button><button id="pitch-up" title="升高半音" aria-label="升高半音" disabled>↑</button><button id="pitch-down" title="降低半音" aria-label="降低半音" disabled>↓</button><button id="move-earlier" title="按当前网格提前起音" aria-label="提前起音" disabled>←</button><button id="move-later" title="按当前网格延后起音" aria-label="延后起音" disabled>→</button><button id="shorter" disabled>缩短</button><button id="longer" disabled>延长</button><button id="split" disabled>拆分</button><button id="merge" disabled>与后音合并</button><button id="delete-note" disabled>删除</button></div><output id="playback-state" class="playback-state" aria-live="polite"></output>`,
  );
const playbackTools = document.createElement("div");
playbackTools.className = "playback-tools";
playbackTools.innerHTML = `<select id="playback-start" aria-label="播放起点"><option value="beginning">从头播放</option><option value="selected">从选中音符开始</option></select><select id="playback-speed" aria-label="播放速度"><option value="0.5">速度 50%</option><option value="0.6">速度 60%</option><option value="0.75">速度 75%</option><option value="0.85">速度 85%</option><option value="1" selected>速度 100%</option><option value="1.1">速度 110%</option><option value="1.25">速度 125%</option><option value="1.5">速度 150%</option></select>`;
for (const selector of [
  "#playback-version",
  "#playback-mode",
  ".playback-loop",
  "#play",
]) {
  const control = document.querySelector(selector);
  if (control) playbackTools.append(control);
}
document.querySelector(".score-tools")!.insertBefore(
  playbackTools,
  document.querySelector(".edit-actions"),
);
document
  .querySelector(".toolbar")!
  .insertAdjacentHTML(
    "afterend",
    `<section class="playback-controls"><p class="context-help"><strong>演唱版</strong>保留真实演唱时间；<strong>谱面版</strong>对齐节拍网格，适合阅读和演奏。</p><label>谱面音量 <output id="score-volume-value">80%</output><input id="score-volume" type="range" min="0" max="100" value="80"></label><label>原曲音量 <output id="source-volume-value">35%</output><input id="source-volume" type="range" min="0" max="100" value="35"></label><label>人声音量 <output id="vocal-volume-value">55%</output><input id="vocal-volume" type="range" min="0" max="100" value="55"></label><label>音频偏移 ms <input id="audio-offset" type="number" min="-2000" max="2000" step="10" value="0"></label><button id="auto-align" type="button">估算并应用对齐</button><small>只做统一平移，不改变 tempo 或音符时值</small><output id="alignment-result"></output></section><section class="waveform-panel"><span>源音频波形</span><canvas id="waveform" width="900" height="100"></canvas></section>`,
  );
document
  .querySelector(".tabs")!
  .insertAdjacentHTML(
    "beforeend",
    `<button data-view="piano">钢琴卷帘</button>`,
  );
document
  .querySelector("#staff")!
  .insertAdjacentHTML(
    "beforebegin",
    `<div id="piano" class="score piano-roll hidden"></div>`,
  );
document
  .querySelector("#piano")!
  .insertAdjacentHTML(
    "beforebegin",
    `<div id="roll-zoom" class="hidden"><label>缩放 <input id="zoom" type="range" min="1" max="8" step="0.1" value="1"></label><output id="zoom-value">100%</output><label id="f0-toggle" class="hidden"><input id="show-f0" type="checkbox" checked> F0</label></div>`,
  );

const $ = <T extends HTMLElement>(s: string) => document.querySelector<T>(s)!;
const taskProgress = new TaskProgressPanel($("#task-progress"));
const input = $<HTMLInputElement>("#file"),
  audio = $<HTMLAudioElement>("#audio"),
  transcribe = $<HTMLButtonElement>("#transcribe"),
  bpm = $<HTMLInputElement>("#bpm"),
  meter = $<HTMLSelectElement>("#meter"),
  key = $<HTMLSelectElement>("#key"),
  mode = $<HTMLSelectElement>("#mode"),
  play = $<HTMLButtonElement>("#play");
meter.innerHTML = `<option value="2/4">2 / 4</option><option value="3/4">3 / 4</option><option value="4/4">4 / 4</option><option value="6/8">6 / 8</option>`;
meter.value = "4/4";
transcribe.insertAdjacentHTML(
  "afterend",
  `<button class="ghost" id="retry-job" disabled>重试上次失败任务</button>`,
);
transcribe.insertAdjacentHTML(
  "afterend",
  `<button class="ghost hidden" id="cancel-job">取消任务</button>`,
);
$(".waveform-panel").insertAdjacentHTML(
  "afterend",
  `<section id="vocal-preview" class="waveform-panel"></section><section class="melody-controls"><label>旋律整理<select id="melody-mode"><option value="balanced">主旋律 · 均衡</option><option value="conservative">主旋律 · 保守</option><option value="raw">原始识别</option></select></label><label>最低音 MIDI<input id="melody-low" type="number" min="0" max="127" value="48"></label><label>最高音 MIDI<input id="melody-high" type="number" min="0" max="127" value="84"></label><button id="refine-melody" disabled>应用整理</button><output id="melody-result"></output></section>`,
);
$(".melody-controls").insertAdjacentHTML(
  "afterend",
  `<section class="quantization-controls"><p class="context-help"><strong>量化</strong>只修改谱面版，把音符吸附到节拍网格；演唱版的真实时间不会改变。</p><label class="toggle"><input id="quantize-enabled" type="checkbox" checked> 量化</label><label>网格<select id="quantize-grid"><option value="0.125">1/8 拍</option><option value="0.16666666666666666">六连音</option><option value="0.25" selected>1/4 拍</option><option value="0.3333333333333333">三连音</option><option value="0.5">1/2 拍</option><option value="1">1 拍</option></select></label><label>强度 <output id="quantize-strength-value">100%</output><input id="quantize-strength" type="range" min="0" max="100" value="100"></label><label>节拍偏移 ms<input id="quantize-offset" type="number" min="-10000" max="10000" value="0"></label><button id="apply-quantization" disabled>应用量化</button><output id="quantization-result"></output></section>`,
);
$(".quantization-controls").insertAdjacentHTML(
  "afterend",
    `<section id="boundary-review" class="boundary-review hidden" aria-label="F0 止音建议"><header><strong>止音建议</strong><output id="boundary-summary"></output></header><p class="context-help">根据 F0 发声证据提示音符可能应提前或延后结束，只在接受后修改音符。</p><div class="boundary-batch"><label>自动接受阈值 <output id="boundary-threshold-value">85%</output><input id="boundary-threshold" type="range" min="0" max="100" value="85"></label><button id="preview-boundaries" type="button">预览高置信建议</button><button id="accept-boundaries" type="button">批量接受</button><button id="reset-boundaries" type="button">撤销最近批次</button><output id="boundary-batch-result"></output></div><div id="boundary-list"></div></section>`,
);
const vocalPreview = new VocalPreview(audio, $("#vocal-preview"));
$("#vocal-preview").insertAdjacentHTML(
  "afterend",
  `<section id="transcription-diagnostics" class="diagnostics hidden" aria-label="转谱输入诊断"></section>`,
);
audio.insertAdjacentHTML(
  "afterend",
  `<div class="field"><label>处理引擎</label><select id="engine"><option value="server-high">Basic Pitch · Demucs</option><option value="server-experimental" selected>GAME + F0 · 推荐</option><option value="server-demo">后端演示 · 快速</option><option value="local">浏览器本地模式</option></select><small>GAME + F0 需要 quality Worker，未配置时不会静默回退</small></div>`,
);
document
  .querySelector("aside")!
  .insertAdjacentHTML(
    "afterbegin",
    `<div class="recent-projects"><button id="project-picker" type="button" aria-haspopup="dialog">项目 / 谱面</button></div><dialog id="project-dialog" aria-labelledby="project-dialog-title"><div class="project-dialog-content"><header><strong id="project-dialog-title">项目 / 谱面</strong><div class="dialog-title-actions"><button id="refresh-projects" type="button" title="刷新项目" aria-label="刷新项目">↻</button><button id="bulk-delete-projects" type="button" title="批量删除谱面" aria-label="批量删除谱面" disabled>⌫</button><button id="close-project-dialog" type="button" title="关闭" aria-label="关闭">×</button></div></header><div id="project-list" class="project-list"></div><select id="recent-project" class="project-selection-proxy" multiple aria-hidden="true" tabindex="-1"><option value="">选择已保存项目…</option></select><button id="rename-project" class="hidden" type="button" title="重命名项目" disabled>项目名</button><button id="rename-score" class="hidden" type="button" title="重命名谱面" disabled>谱名</button><button id="delete-project" class="hidden" type="button" title="删除谱面" disabled>删除</button><div class="project-upload" aria-label="创建新项目"></div></div></dialog>`,
  );
document.querySelector(".project-upload")!.append(document.querySelector("#drop")!);
$("#project-picker").addEventListener("click", () =>
  $<HTMLDialogElement>("#project-dialog").showModal(),
);
$("#close-project-dialog").addEventListener("click", () =>
  $<HTMLDialogElement>("#project-dialog").close(),
);
$("#project-dialog").addEventListener("click", (event) => {
  if (event.target === $("#project-dialog"))
    $<HTMLDialogElement>("#project-dialog").close();
});
$("#project-list").addEventListener("change", (event) => {
  const checkbox = (event.target as HTMLElement).closest<HTMLInputElement>(
    "[data-score-select]",
  );
  if (!checkbox) return;
  const option = $<HTMLSelectElement>("#recent-project").querySelector<HTMLOptionElement>(
    `option[value="${CSS.escape(checkbox.dataset.scoreSelect ?? "")}"]`,
  );
  if (option) option.selected = checkbox.checked;
  $<HTMLButtonElement>("#bulk-delete-projects").disabled =
    ![...$<HTMLSelectElement>("#recent-project").selectedOptions].some((item) => item.value);
});
$("#project-list").addEventListener("click", (event) => {
  const projectAction = (event.target as HTMLElement).closest<HTMLButtonElement>(
    "[data-project-action]",
  );
  if (projectAction) {
    event.preventDefault();
    event.stopPropagation();
    const card = projectAction.closest<HTMLElement>(".project-card");
    const groupId = card?.dataset.projectGroup;
    if (!card || !groupId) return;
    if (projectAction.dataset.projectAction === "edit")
      startInlineNameEdit("project", groupId, card.querySelector(".project-name"), card.querySelector(".row-actions"));
    else void deleteProjectGroup(
      groupId,
      [...card.querySelectorAll<HTMLElement>("[data-score-id]")]
        .map((item) => item.dataset.scoreId!)
        .filter(Boolean),
    );
    return;
  }
  const scoreAction = (event.target as HTMLElement).closest<HTMLButtonElement>(
    "[data-score-action]",
  );
  if (scoreAction) {
    event.preventDefault();
    event.stopPropagation();
    const scoreId = scoreAction.dataset.scoreId;
    const row = scoreAction.closest<HTMLElement>(".score-row");
    if (!scoreId || !row) return;
    if (scoreAction.dataset.scoreAction === "edit")
      startInlineNameEdit("score", scoreId, row.querySelector(".score-name"), row.querySelector(".row-actions"));
    else void deleteScore(scoreId);
    return;
  }
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
    "[data-score-id]",
  );
  if (!button) return;
  const select = $<HTMLSelectElement>("#recent-project");
  select.value = button.dataset.scoreId ?? "";
  select.dispatchEvent(new Event("change", { bubbles: true }));
});
let sourceBuffer: AudioBuffer | null = null,
  sourceFile: File | null = null,
  activeUploadId: string | null = null,
  activeUploadName: string | null = null,
  serverProject: ApiScoreProject | null = null,
  rawNotes: RawNote[] = [],
  notes: ScoreNote[] = [];
let selectedNoteIndex: number | null = null;
let scoreHistory: ScoreHistory | null = null;
let f0Frames: F0Frame[] = [];
let f0ProjectId: string | null = null;
function clearF0Evidence() {
  f0Frames = [];
  f0ProjectId = null;
  $("#f0-toggle").classList.add("hidden");
}
let analysis: MusicalAnalysis = {
  bpm: 120,
  meter: 4,
  meterDenominator: 4,
  keyPitchClass: 0,
  mode: "major",
  confidence: { bpm: 0, meter: 0, key: 0 },
};
let tempoMap: Array<{ time_ms: number; bpm: number }> = [
  { time_ms: 0, bpm: 120 },
];
const scorePlayer = new ScorePlayer();
let playing = false;
let syncingAudio = false;
let syncedAudioRange: { start: number; end: number; loop: boolean } | null = null;
let sourceAudioUrl = "";
let vocalsAudioUrl = "";
let transcriptionBusy = false;
let taskAbort: AbortController | null = null;
let activeJobId: string | null = null;
let cancelRequested = false;
let localOriginalNotes: RawNote[] = [];
let loadVersion = 0;
function checkTaskCancelled() {
  if (cancelRequested || taskAbort?.signal.aborted)
    throw new DOMException("任务已取消", "AbortError");
}
function handleCancellation(error: unknown) {
  if (!(error instanceof DOMException && error.name === "AbortError"))
    return false;
  taskProgress.cancel();
  status("任务已取消");
  return true;
}
async function cancelSubmittedJob(id: string) {
  if (!cancelRequested) return;
  try {
    await api.cancelJob(id);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 409) throw error;
    cancelRequested = false;
  }
}
function setTranscriptionBusy(busy: boolean) {
  if (busy) {
    taskAbort = new AbortController();
    cancelRequested = false;
  } else {
    taskAbort = null;
    activeJobId = null;
  }
  transcriptionBusy = busy;
  transcribe.disabled = busy || !sourceBuffer;
  input.disabled = busy;
  $<HTMLSelectElement>("#engine").disabled = busy;
  $<HTMLSelectElement>("#recent-project").disabled = busy;
  $<HTMLButtonElement>("#example").disabled = busy;
  $<HTMLButtonElement>("#delete-project").disabled =
    busy || !$<HTMLSelectElement>("#recent-project").value;
  $<HTMLButtonElement>("#rename-project").disabled =
    busy || !$<HTMLSelectElement>("#recent-project").value;
  $<HTMLButtonElement>("#rename-score").disabled =
    busy || !$<HTMLSelectElement>("#recent-project").value;
  $<HTMLButtonElement>("#bulk-delete-projects").disabled = busy || !$<HTMLSelectElement>("#recent-project").value;
  $<HTMLButtonElement>("#retry-job").disabled =
    busy || !localStorage.getItem(FAILED_JOB_KEY);
  $("#cancel-job").classList.toggle("hidden", !busy);
  $<HTMLButtonElement>("#cancel-job").disabled = false;
  $<HTMLButtonElement>("#refine-melody").disabled =
    busy ||
    (!notes.length &&
      !localOriginalNotes.length &&
      !serverProject?.raw_notes?.length);
}
$("#cancel-job").addEventListener("click", async () => {
  cancelRequested = true;
  $<HTMLButtonElement>("#cancel-job").disabled = true;
  status("正在取消任务…");
  try {
    if (activeJobId) {
      try {
        taskProgress.updateJob(await api.cancelJob(activeJobId));
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 409) throw error;
        const current = await api.getJob(activeJobId);
        if (current.status === "completed") {
          cancelRequested = false;
          status("任务已完成，正在载入结果…");
          return;
        }
      }
    } else taskAbort?.abort();
  } catch (error) {
    cancelRequested = false;
    $<HTMLButtonElement>("#cancel-job").disabled = false;
    status(`取消失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
});
function status(message: string) {
  $("#status").textContent = message;
}
const conf = (v: number) =>
  v < 0.4 ? "低置信度 · 建议校正" : v < 0.7 ? "中等置信度" : "高置信度";
async function load(file: File) {
  if (transcriptionBusy) return;
  const version = ++loadVersion;
  stop();
  scoreHistory = null;
  selectedNoteIndex = null;
  rawNotes = [];
  notes = [];
  void render();
  taskProgress.reset();
  status("正在解码音频…");
  sourceFile = file;
  activeUploadId = null;
  activeUploadName = null;
  serverProject = null;
  syncQuantization(null);
  clearF0Evidence();
  vocalPreview.setSource(URL.createObjectURL(file));
  localOriginalNotes = [];
  sourceBuffer = await new AudioContext().decodeAudioData(
    await file.arrayBuffer(),
  );
  if (version !== loadVersion) return;
  drawWaveform($<HTMLCanvasElement>("#waveform"), sourceBuffer);
  transcribe.disabled = true;
  status(`已载入 ${file.name}，正在创建项目…`);
  try {
    const upload = await api.upload(file);
    if (version !== loadVersion) return;
    activeUploadId = upload.id;
    activeUploadName = upload.project_name || file.name;
    $("#project-picker").textContent = activeUploadName;
    await refreshProjects();
    transcribe.disabled = false;
    status(`已创建项目 ${upload.project_name || file.name} · ${sourceBuffer.duration.toFixed(1)} 秒`);
  } catch (error) {
    if (version !== loadVersion) return;
    transcribe.disabled = false;
    status(`项目创建失败，扒谱时将重试：${error instanceof Error ? error.message : "未知错误"}`);
  }
}
input.addEventListener(
  "change",
  () => input.files?.[0] && load(input.files[0]),
);
const drop = $("#drop");
drop.addEventListener("dragover", (e) => {
  e.preventDefault();
  drop.classList.add("over");
});
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  const f = e.dataTransfer?.files[0];
  if (f) load(f);
});
const isolate = $<HTMLInputElement>("#isolate");
const isolateField = isolate.closest<HTMLElement>(".field")!;
isolateField.id = "local-isolate-field";
isolate.addEventListener(
  "input",
  () => ($("#isolateValue").textContent = `${isolate.value}%`),
);
function syncEngineControls() {
  isolateField.classList.toggle(
    "hidden",
    $<HTMLSelectElement>("#engine").value !== "local",
  );
}
$<HTMLSelectElement>("#engine").addEventListener("change", syncEngineControls);
syncEngineControls();
async function infer(buffer: AudioBuffer) {
  checkTaskCancelled();
  const signal = taskAbort!.signal;
  const worker = new Worker(new URL("./inference.worker.ts", import.meta.url), {
    type: "module",
  });
  return new Promise<RawNote[]>((resolve, reject) => {
    const finish = () => {
      worker.terminate();
      signal.removeEventListener("abort", cancel);
    };
    const cancel = () => {
      finish();
      reject(new DOMException("任务已取消", "AbortError"));
    };
    signal.addEventListener("abort", cancel, { once: true });
    worker.onerror = (event) => {
      finish();
      reject(new Error(event.message));
    };
    worker.onmessage = (event) => {
      if (event.data.error) {
        finish();
        reject(new Error(event.data.error));
      } else if (event.data.notes) {
        finish();
        resolve(event.data.notes);
      } else
        taskProgress.start(
          "transcribe",
          "正在识别人声旋律",
          event.data.progress * 100,
        );
    };
    const samples = buffer.getChannelData(0).slice();
    worker.postMessage(
      {
        samples,
        threshold: Number($<HTMLSelectElement>("#sensitivity").value),
        modelUrl: `${location.origin}/basic-pitch-model/model.json`,
      },
      [samples.buffer],
    );
  });
}
async function runLocal() {
  if (!sourceBuffer) return;
  stop();
  serverProject = null;
  syncQuantization(null);
  clearF0Evidence();
  scoreHistory = null;
  selectedNoteIndex = null;
  taskProgress.start("separate", "提取中心人声与增强语音频段");
  status("正在提取中心人声与增强语音频段…");
  const isolated = await isolateCenterVocal(
    sourceBuffer,
    Number(isolate.value) / 100,
  );
  checkTaskCancelled();
  vocalPreview.setVocals(URL.createObjectURL(audioBlob(isolated)), isolated);
  taskProgress.start("separate", "正在重采样人声");
  status("正在重采样人声…");
  const vocal = await resampleAudio(isolated);
  checkTaskCancelled();
  taskProgress.start("transcribe", "正在加载音高模型");
  status("正在加载音高模型…");
  rawNotes = await infer(vocal);
  checkTaskCancelled();
  localOriginalNotes = rawNotes.map((n) => ({ ...n }));
  taskProgress.start("transcribe", "正在分析 BPM、拍号与调性");
  status("正在分析 BPM、拍号与调性…");
  analysis = analyzeMusic(sourceBuffer, rawNotes);
  tempoMap = [{ time_ms: 0, bpm: analysis.bpm }];
  applyLocalRefinement();
}
function applyApiProject(project: ApiScoreProject) {
  stop();
  activeUploadId = project.project_group_id ?? activeUploadId;
  activeUploadName = project.project_name ?? project.source.file_name;
  selectedNoteIndex = null;
  scoreHistory = new ScoreHistory(project.notes);
  const tempo = project.analysis.tempo_map[0];
  tempoMap = project.analysis.tempo_map.length
    ? project.analysis.tempo_map.map((point) => ({ ...point }))
    : [{ time_ms: 0, bpm: tempo?.bpm ?? 120 }];
  const meterPoint = project.analysis.meter_map[0];
  const keyPoint = project.analysis.key_map[0];
  rawNotes = (project.performance_notes ?? project.notes).map((note) => ({
    pitchMidi: note.pitch_midi,
    amplitude: note.confidence,
    startTimeSeconds: note.source_start_ms / 1000,
    durationSeconds: (note.source_end_ms - note.source_start_ms) / 1000,
  }));
  analysis = {
    bpm: tempo?.bpm ?? 120,
    meter: ([2, 3, 4, 6].includes(meterPoint?.numerator ?? 4)
      ? meterPoint?.numerator
      : 4) as 2 | 3 | 4 | 6,
    meterDenominator: meterPoint?.denominator === 8 ? 8 : 4,
    keyPitchClass: keyPoint?.tonic ?? 0,
    mode: keyPoint?.mode ?? "major",
    confidence: {
      bpm: project.analysis.confidence.tempo ?? 0,
      meter: project.analysis.confidence.meter ?? 0,
      key: project.analysis.confidence.key ?? 0,
    },
  };
  syncQuantization(project);
  renderTempoMap();
  $<HTMLInputElement>("#audio-offset").value = String(project.audio_alignment?.offset_ms ?? 0);
  const diagnostic = project.transcription_diagnostics;
  const panel = $("#transcription-diagnostics");
  panel.classList.toggle("hidden", !diagnostic);
  if (diagnostic) {
    panel.innerHTML = `<strong>转谱输入诊断</strong><span>输入：${project.transcription_input?.variant === "vocal_stem" ? "Demucs 分离人声" : "原始音频"}</span><span>时长：${(diagnostic.input_duration_ms / 1000).toFixed(1)} 秒</span><span>开头低能量：${(diagnostic.leading_silence_ms / 1000).toFixed(2)} 秒</span><span>低能量区音符：${diagnostic.low_energy_note_count} 个</span><span>开头低能量区音符：${diagnostic.notes_in_leading_silence} 个</span>`;
  }
}
function boundaryTime(milliseconds: number) {
  const minutes = Math.floor(milliseconds / 60_000);
  const seconds = ((milliseconds % 60_000) / 1000).toFixed(2).padStart(5, "0");
  return `${minutes}:${seconds}`;
}
function reviewActions(suggestion: BoundarySuggestion) {
  const encodedId = encodeURIComponent(suggestion.id);
  if (suggestion.review_status === "pending")
    return `<button data-boundary-action="accept" data-suggestion-id="${encodedId}" title="接受建议" aria-label="接受建议">✓</button><button data-boundary-action="reject" data-suggestion-id="${encodedId}" title="忽略建议" aria-label="忽略建议">×</button>`;
  if (suggestion.review_status === "superseded")
    return `<span class="boundary-state superseded" title="${boundarySupersededLabel(suggestion)}">已被人工编辑替代</span>`;
  const label = suggestion.review_status === "accepted" ? "已接受" : "已忽略";
  return `<span class="boundary-state ${suggestion.review_status}">${label}</span><button data-boundary-action="reset" data-suggestion-id="${encodedId}" title="撤销审阅" aria-label="撤销审阅">↶</button>`;
}
function renderBoundaryReview() {
  const panel = $("#boundary-review");
  const suggestions = serverProject
    ? reviewableBoundarySuggestions(
        serverProject.transcription_evidence?.boundary_suggestions ?? [],
        serverProject.notes,
      )
    : [];
  panel.classList.toggle("hidden", suggestions.length === 0);
  if (!suggestions.length) {
    $("#boundary-list").innerHTML = "";
    return;
  }
  const pendingSuggestions = suggestions.filter(
    (suggestion) => suggestion.review_status === "pending",
  );
  const pending = pendingSuggestions.length;
  const accepted = suggestions.filter(
    (suggestion) => suggestion.review_status === "accepted",
  ).length;
  const superseded = suggestions.filter(
    (suggestion) => suggestion.review_status === "superseded",
  ).length;
  const rejected = suggestions.length - pending - accepted - superseded;
  $("#boundary-summary").textContent =
    `${pending} 待审 · ${accepted} 已接受 · ${rejected} 已忽略 · ${superseded} 已替代`;
  $("#boundary-list").innerHTML = orderedBoundarySuggestions(suggestions)
    .map(
      (suggestion) =>
        `<div class="boundary-row"><button class="boundary-locate" data-boundary-locate="${encodeURIComponent(suggestion.source_note_id)}" title="定位并试听" aria-label="定位并试听">▶</button><div class="boundary-change"><strong>${boundaryTime(suggestion.original_end_ms)} → ${boundaryTime(suggestion.proposed_end_ms)}</strong><span>${boundaryReasonLabel(suggestion)} · ${boundaryDeltaLabel(suggestion)}</span></div><meter min="0" max="1" value="${suggestion.confidence}" title="F0 置信度 ${Math.round(suggestion.confidence * 100)}%"></meter><output>${Math.round(suggestion.confidence * 100)}%</output><div class="boundary-actions">${reviewActions(suggestion)}</div></div>`,
    )
    .join("");
  const threshold = Number($<HTMLInputElement>("#boundary-threshold").value) / 100;
  const eligible = pendingSuggestions.filter(
    (suggestion) => suggestion.confidence >= threshold,
  ).length;
  $("#boundary-batch-result").textContent = `${eligible} 条建议达到阈值`;
  $<HTMLButtonElement>("#accept-boundaries").disabled = editSaving || transcriptionBusy || eligible === 0;
  const hasBatch = Boolean(
    serverProject?.transcription_evidence?.last_boundary_batch_id,
  );
  $<HTMLButtonElement>("#reset-boundaries").disabled = editSaving || transcriptionBusy || !hasBatch;
  panel
    .querySelectorAll<HTMLButtonElement>("button")
    .forEach((button) => (button.disabled = editSaving || transcriptionBusy));
}
async function loadServerAudio(project: ApiScoreProject) {
  const url = api.audioUrl(project.project_id);
  sourceAudioUrl = url;
  vocalsAudioUrl = project.source.vocal_object_key ? api.audioUrl(project.project_id, "vocals") : "";
  vocalPreview.setSource(url);
  vocalPreview.setVocals(
    vocalsAudioUrl,
  );
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error("源音频不可用");
    const bytes = await response.arrayBuffer();
    const decoded = await new AudioContext().decodeAudioData(bytes.slice(0));
    if (serverProject?.project_id !== project.project_id) return;
    sourceFile = new File([bytes], project.source.file_name, {
      type: response.headers.get("content-type") || "audio/wav",
    });
    sourceBuffer = decoded;
    transcribe.disabled = transcriptionBusy;
    drawWaveform($<HTMLCanvasElement>("#waveform"), sourceBuffer);
  } catch {
    sourceBuffer = null;
    sourceFile = null;
    transcribe.disabled = true;
  }
}
async function loadF0Evidence(project: ApiScoreProject) {
  const artifact = project.transcription_evidence?.f0_track;
  f0ProjectId = project.project_id;
  f0Frames = [];
  $("#f0-toggle").classList.toggle("hidden", !artifact);
  if (!artifact) return;
  try {
    const frames = await api.getF0Track(project.project_id);
    if (serverProject?.project_id !== project.project_id) return;
    f0Frames = frames;
  } catch (error) {
    if (serverProject?.project_id !== project.project_id) return;
    $("#f0-toggle").classList.add("hidden");
    if (!(error instanceof ApiError) || error.status !== 404)
      status(
        `F0 轨迹加载失败：${error instanceof Error ? error.message : "未知错误"}`,
      );
  }
}
async function recoverRevisionConflict(error: unknown) {
  if (!(error instanceof ApiError) || error.status !== 409 || !serverProject)
    return false;
  serverProject = await api.getProject(serverProject.project_id);
  applyApiProject(serverProject);
  sync();
  void render();
  status(`检测到其他页面的修改，已恢复最新修订 ${serverProject.revision}`);
  return true;
}
async function runServer(quality: "demo" | "high" | "experimental") {
  if (!sourceFile) return;
  taskProgress.start("prepare", "正在上传音频");
  let uploadId = activeUploadId ?? serverProject?.project_group_id;
  if (!uploadId) {
    status("正在上传音频…");
    uploadId = (await api.upload(sourceFile, taskAbort?.signal)).id;
    activeUploadId = uploadId;
    checkTaskCancelled();
  } else {
    status("复用当前项目的原始音频…");
  }
  taskProgress.start("prepare", "正在提交处理任务");
  status("已进入后端处理队列…");
  const submitted = await api.createJob(uploadId, quality);
  localStorage.setItem(ACTIVE_JOB_KEY, submitted.id);
  activeJobId = submitted.id;
  await cancelSubmittedJob(submitted.id);
  const job = await waitForServerJob(submitted.id);
  if (!job.project_id) throw new Error("后端未返回乐谱项目");
  serverProject = await api.getProject(job.project_id);
  applyApiProject(serverProject);
  await Promise.all([
    loadServerAudio(serverProject),
    loadF0Evidence(serverProject),
  ]);
  void refreshProjects();
}
async function waitForServerJob(jobId: string) {
  activeJobId = jobId;
  let terminal = false;
  let cancelled = false;
  try {
    const job = await api.waitForJobEvents(jobId, (current) => {
      terminal = ["completed", "failed", "cancelled"].includes(current.status);
      cancelled = current.status === "cancelled";
      if (current.status === "completed")
        taskProgress.start("transcribe", "正在载入乐谱");
      else taskProgress.updateJob(current);
      status(
        current.status === "failed"
          ? "任务处理失败"
          : JOB_STAGE_LABELS[current.stage],
      );
    });
    localStorage.removeItem(FAILED_JOB_KEY);
    $<HTMLButtonElement>("#retry-job").disabled = true;
    return job;
  } catch (error) {
    if (cancelled) {
      localStorage.removeItem(FAILED_JOB_KEY);
      throw new DOMException("任务已取消", "AbortError");
    }
    if (error instanceof ApiError && error.status === 404) {
      terminal = true;
      taskProgress.fail("原任务已不存在，请重新开始");
      throw new Error("原任务已不存在，请重新开始");
    }
    if (!terminal) {
      taskProgress.interrupt();
      throw new Error("进度连接中断，刷新页面可恢复");
    }
    localStorage.setItem(FAILED_JOB_KEY, jobId);
    throw error;
  } finally {
    if (terminal) localStorage.removeItem(ACTIVE_JOB_KEY);
  }
}
$("#retry-job").addEventListener("click", async () => {
  const failedJobId = localStorage.getItem(FAILED_JOB_KEY);
  if (!failedJobId || transcriptionBusy) return;
  setTranscriptionBusy(true);
  taskProgress.reset();
  taskProgress.start("prepare", "正在重新提交任务");
  try {
    status("正在重新提交任务…");
    const submitted = await api.retryJob(failedJobId);
    localStorage.setItem(ACTIVE_JOB_KEY, submitted.id);
    activeJobId = submitted.id;
    await cancelSubmittedJob(submitted.id);
    const job = await waitForServerJob(submitted.id);
    if (!job.project_id) throw new Error("重试任务没有乐谱项目");
    serverProject = await api.getProject(job.project_id);
    applyApiProject(serverProject);
    await Promise.all([
      loadServerAudio(serverProject),
      loadF0Evidence(serverProject),
    ]);
    sync();
    await render();
    taskProgress.complete();
    void refreshProjects();
    status("重试任务已完成");
  } catch (error) {
    if (handleCancellation(error)) return;
    taskProgress.fail(error instanceof Error ? error.message : "未知错误");
    status(`重试失败：${error instanceof Error ? error.message : "未知错误"}`);
  } finally {
    setTranscriptionBusy(false);
  }
});
async function resumeActiveJob() {
  const jobId = localStorage.getItem(ACTIVE_JOB_KEY);
  if (!jobId) return;
  setTranscriptionBusy(true);
  taskProgress.start("prepare", "正在恢复任务进度");
  try {
    status("正在恢复未完成任务…");
    const job = await waitForServerJob(jobId);
    if (!job.project_id) throw new Error("恢复的任务没有乐谱项目");
    serverProject = await api.getProject(job.project_id);
    applyApiProject(serverProject);
    await Promise.all([
      loadServerAudio(serverProject),
      loadF0Evidence(serverProject),
    ]);
    sync();
    await render();
    taskProgress.complete();
    status(
      `任务已恢复 · ${serverProject.source.file_name} · ${serverProject.notes.length} 个音符`,
    );
  } catch (error) {
    if (handleCancellation(error)) return;
    taskProgress.fail(error instanceof Error ? error.message : "未知错误");
    status(
      `任务恢复失败：${error instanceof Error ? error.message : "未知错误"}`,
    );
  } finally {
    setTranscriptionBusy(false);
  }
}
async function refreshProjects() {
  const select = $<HTMLSelectElement>("#recent-project");
  try {
    const projects = await api.listProjectCatalog();
    select.innerHTML =
      `<option value="">选择已保存项目…</option>` +
      projects
        .filter(
          (project): project is ProjectCatalogSummary & { project_id: string } =>
            Boolean(project.project_id),
        )
        .map(
          (project) =>
            `<option value="${project.project_id}">${project.project_name} / ${project.score_name} · ${project.engine} · ${project.note_count} 音符</option>`,
        )
        .join("");
    if (serverProject) select.value = serverProject.project_id;
    renderProjectCatalog(projects);
    const activeUpload = projects.find(
      (project) => project.upload_id === activeUploadId,
    );
    $("#project-picker").textContent = serverProject
      ? `${serverProject.project_name ?? "未命名项目"} / ${serverProject.score_name ?? "未命名谱面"}`
      : activeUpload?.project_name ?? activeUploadName ?? "项目 / 谱面";
  } catch {
    select.innerHTML = `<option value="">后端项目不可用</option>`;
  }
}
function renderProjectCatalog(projects: ProjectCatalogSummary[]) {
  const groups = new Map<string, ProjectCatalogSummary[]>();
  for (const project of projects) {
    const group = groups.get(project.project_group_id) ?? [];
    group.push(project);
    groups.set(project.project_group_id, group);
  }
  $("#project-list").innerHTML = [...groups.entries()]
    .map(([groupId, scores]) => {
      const projectName = scores[0].project_name || "未命名项目";
      const open = groupId === activeUploadId || scores.some((score) => score.project_id === serverProject?.project_id)
        ? " open"
        : "";
      const generatedScores = scores.filter(
        (score): score is ProjectCatalogSummary & { project_id: string } =>
          Boolean(score.project_id),
      );
      const scoreRows = generatedScores.length
        ? generatedScores
          .map(
            (score) =>
              `<div class="score-row"><label class="score-select"><input data-score-select="${escapeHtml(score.project_id)}" type="checkbox" aria-label="选择 ${escapeHtml(score.score_name || "未命名谱面")}"></label><button class="score-option${score.project_id === serverProject?.project_id ? " selected" : ""}" data-score-id="${escapeHtml(score.project_id)}" type="button"><span class="score-name">${escapeHtml(score.score_name || "未命名谱面")}</span><small>${escapeHtml(score.engine || "未知引擎")} · ${score.note_count} 音符</small></button><span class="row-actions"><button data-score-action="edit" data-score-id="${escapeHtml(score.project_id)}" type="button" title="修改谱面名称" aria-label="修改谱面名称">✎</button><button data-score-action="delete" data-score-id="${escapeHtml(score.project_id)}" type="button" title="删除谱面" aria-label="删除谱面">⌫</button></span></div>`,
          )
          .join("")
        : `<p class="empty-score-list">尚未生成谱面</p>`;
      return `<details class="project-card" data-project-group="${escapeHtml(groupId)}"${open}><summary><span class="project-name">${escapeHtml(projectName)}</span><small>${generatedScores.length} 份谱面</small><span class="row-actions"><button data-project-action="edit" type="button" title="修改项目名称" aria-label="修改项目名称">✎</button><button data-project-action="delete" type="button" title="删除项目" aria-label="删除项目">⌫</button></span></summary><div class="score-list">${scoreRows}</div></details>`;
    })
    .join("");
}
function escapeHtml(value: string) {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ] ?? character,
  );
}
function startInlineNameEdit(
  kind: "project" | "score",
  id: string,
  nameElement: Element | null,
  actionsElement: Element | null,
) {
  if (!nameElement || !actionsElement || nameElement.querySelector("input")) return;
  const input = document.createElement("input");
  input.className = "inline-name-input";
  input.value = nameElement.textContent?.trim() ?? "";
  input.maxLength = 255;
  nameElement.replaceChildren(input);
  actionsElement.innerHTML = `<button data-name-action="save" type="button" title="保存名称" aria-label="保存名称">✓</button><button data-name-action="cancel" type="button" title="取消修改" aria-label="取消修改">×</button>`;
  input.focus();
  input.select();
  const finish = async (save: boolean) => {
    if (!save) {
      await refreshProjects();
      return;
    }
    const name = input.value.trim();
    if (!name) return input.focus();
    try {
      if (kind === "project") {
        await api.renameAudioProject(id, name);
        if (serverProject?.project_group_id === id)
          serverProject = await api.getProject(serverProject.project_id);
      } else {
        const project = serverProject?.project_id === id
          ? serverProject
          : await api.getProject(id);
        const renamed = await api.renameProject(id, project.revision, name);
        if (serverProject?.project_id === id) serverProject = renamed;
      }
      await refreshProjects();
      if (serverProject)
        $("#project-picker").textContent = `${serverProject.project_name ?? "未命名项目"} / ${serverProject.score_name ?? "未命名谱面"}`;
      status(kind === "project" ? "项目名称已更新" : "谱面名称已更新");
    } catch (error) {
      status(`名称更新失败：${error instanceof Error ? error.message : "未知错误"}`);
    }
  };
  actionsElement.querySelector('[data-name-action="save"]')?.addEventListener("click", () => void finish(true));
  actionsElement.querySelector('[data-name-action="cancel"]')?.addEventListener("click", () => void finish(false));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") void finish(true);
    if (event.key === "Escape") void finish(false);
  });
}
async function deleteScore(projectId: string) {
  if (!confirm("确定删除这份谱面吗？")) return;
  try {
    await api.deleteProject(projectId);
    if (serverProject?.project_id === projectId) clearLoadedProject();
    await refreshProjects();
    status("谱面已删除");
  } catch (error) {
    status(`删除失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
}
async function deleteProjectGroup(uploadId: string, projectIds: string[]) {
  if (!confirm("确定删除这个项目及其全部谱面吗？")) return;
  try {
    const result = projectIds.length
      ? await api.bulkDeleteProjects({ project_ids: projectIds })
      : (await api.deleteUpload(uploadId), { deleted_projects: 0 });
    if (serverProject && projectIds.includes(serverProject.project_id)) clearLoadedProject();
    if (activeUploadId === uploadId) {
      activeUploadId = null;
      activeUploadName = null;
    }
    await refreshProjects();
    status(`项目已删除 · ${result.deleted_projects} 份谱面`);
  } catch (error) {
    status(`删除项目失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
}
function clearLoadedProject() {
  stop();
  serverProject = null;
  activeUploadId = null;
  activeUploadName = null;
  scoreHistory = null;
  selectedNoteIndex = null;
  notes = [];
  rawNotes = [];
  tempoMap = [{ time_ms: 0, bpm: 120 }];
  clearF0Evidence();
  $("#project-picker").textContent = "项目 / 谱面";
  $("#transcription-diagnostics").classList.add("hidden");
  void render();
}
$<HTMLSelectElement>("#recent-project").addEventListener(
  "change",
  async (event) => {
    const projectId = (event.currentTarget as HTMLSelectElement).value;
    $<HTMLButtonElement>("#delete-project").disabled = !projectId;
    $<HTMLButtonElement>("#rename-project").disabled = !projectId;
    $<HTMLButtonElement>("#rename-score").disabled = !projectId;
    $<HTMLButtonElement>("#bulk-delete-projects").disabled = !projectId;
    if (!projectId) return;
    taskProgress.reset();
    try {
      status("正在打开已保存项目…");
      serverProject = await api.getProject(projectId);
      activeUploadId = serverProject.project_group_id ?? null;
      activeUploadName = serverProject.project_name ?? serverProject.source.file_name;
      applyApiProject(serverProject);
      await Promise.all([
        loadServerAudio(serverProject),
        loadF0Evidence(serverProject),
      ]);
      sync();
      render();
      status(
        `已恢复 ${serverProject.source.file_name} · 修订 ${serverProject.revision}`,
      );
      $("#project-picker").textContent =
        `${serverProject.project_name ?? "未命名项目"} / ${serverProject.score_name ?? "未命名谱面"}`;
      $<HTMLDialogElement>("#project-dialog").close();
    } catch (error) {
      if (await recoverRevisionConflict(error)) return;
      status(
        `恢复失败：${error instanceof Error ? error.message : "未知错误"}`,
      );
    }
  },
);
$<HTMLInputElement>("#boundary-threshold").addEventListener("input", () => {
  $("#boundary-threshold-value").textContent = `${$<HTMLInputElement>("#boundary-threshold").value}%`;
  renderBoundaryReview();
});
$("#preview-boundaries").addEventListener("click", () => {
  renderBoundaryReview();
  const threshold = Number($<HTMLInputElement>("#boundary-threshold").value);
  status(`已筛选置信度不低于 ${threshold}% 的止音建议`);
});
$("#accept-boundaries").addEventListener("click", async () => {
  if (!serverProject) return;
  const threshold = Number($<HTMLInputElement>("#boundary-threshold").value) / 100;
  const count = (serverProject.transcription_evidence?.boundary_suggestions ?? []).filter(
    (suggestion) => suggestion.review_status === "pending" && suggestion.confidence >= threshold,
  ).length;
  if (!count || !confirm(`将批量接受 ${count} 条止音建议，是否继续？`)) return;
  try {
    serverProject = await api.reviewBoundaryBatch(serverProject.project_id, {
      expected_revision: serverProject.revision,
      threshold,
      action: "accept",
    });
    applyApiProject(serverProject);
    await render();
    status(`已批量接受 ${count} 条止音建议`);
  } catch (error) {
    status(`批量接受失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
});
$("#reset-boundaries").addEventListener("click", async () => {
  if (!serverProject) return;
  try {
    serverProject = await api.reviewBoundaryBatch(serverProject.project_id, {
      expected_revision: serverProject.revision,
      threshold: 0,
      action: "reset",
    });
    applyApiProject(serverProject);
    await render();
    status("已撤销最近一批止音建议");
  } catch (error) {
    status(`撤销失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
});
$("#refresh-projects").addEventListener("click", () => void refreshProjects());
$("#bulk-delete-projects").addEventListener("click", async () => {
  const ids = [...$<HTMLSelectElement>("#recent-project").selectedOptions]
    .map((option) => option.value)
    .filter(Boolean);
  if (!ids.length || !confirm(`确定删除选中的 ${ids.length} 份谱面吗？`)) return;
  try {
    const result = await api.bulkDeleteProjects({ project_ids: ids });
    if (serverProject && ids.includes(serverProject.project_id)) {
      stop();
      serverProject = null;
      scoreHistory = null;
      selectedNoteIndex = null;
      notes = [];
      rawNotes = [];
      clearF0Evidence();
      $("#transcription-diagnostics").classList.add("hidden");
      void render();
    }
    await refreshProjects();
    status(`已删除 ${result.deleted_projects} 份谱面`);
  } catch (error) {
    status(`批量删除失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
});
$("#rename-score").addEventListener("click", async () => {
  if (!serverProject) return;
  const name = prompt("请输入谱面名称", serverProject.score_name ?? "未命名谱面")?.trim();
  if (!name) return;
  try {
    serverProject = await api.renameProject(serverProject.project_id, serverProject.revision, name);
    applyApiProject(serverProject);
    await refreshProjects();
    status("谱面已重命名");
  } catch (error) {
    status(`重命名失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
});
$("#rename-project").addEventListener("click", async () => {
  if (!serverProject?.project_group_id) return;
  const name = prompt("请输入项目名称", serverProject.project_name ?? "未命名项目")?.trim();
  if (!name) return;
  try {
    await api.renameAudioProject(serverProject.project_group_id, name);
    serverProject = await api.getProject(serverProject.project_id);
    await refreshProjects();
    status("项目已重命名");
  } catch (error) {
    status(`重命名失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
});
$("#delete-project").addEventListener("click", async () => {
  const projectId = $<HTMLSelectElement>("#recent-project").value;
  if (
    !projectId ||
    !confirm("确定删除这个项目、源音频和所有处理数据吗？此操作不可撤销。")
  )
    return;
  try {
    await api.deleteProject(projectId);
    if (serverProject?.project_id === projectId) {
      stop();
      serverProject = null;
      syncQuantization(null);
      clearF0Evidence();
      scoreHistory = null;
      selectedNoteIndex = null;
      rawNotes = [];
      notes = [];
      tempoMap = [{ time_ms: 0, bpm: 120 }];
      $("#project-picker").textContent = "项目 / 谱面";
      void render();
      $("#staff").innerHTML = "";
      $("#jianpu").innerHTML = "";
      $("#empty").classList.remove("hidden");
    }
    $<HTMLButtonElement>("#delete-project").disabled = true;
    await refreshProjects();
    taskProgress.reset();
    status("项目及关联数据已删除");
  } catch (error) {
    status(`删除失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
});
transcribe.addEventListener("click", async () => {
  if (!sourceBuffer || transcriptionBusy) return;
  setTranscriptionBusy(true);
  taskProgress.reset();
  taskProgress.start("prepare", "正在准备音频");
  try {
    const engine = $<HTMLSelectElement>("#engine").value;
    if (engine === "server-high") await runServer("high");
    else if (engine === "server-experimental") await runServer("experimental");
    else if (engine === "server-demo") await runServer("demo");
    else await runLocal();
    sync();
    await render();
    taskProgress.complete();
    status(
      `完成 · ${analysis.bpm} BPM · ${analysis.meter}/${analysis.meterDenominator} · ${keyName(analysis.keyPitchClass, analysis.mode)} · ${notes.length} 个音符`,
    );
  } catch (e) {
    if (handleCancellation(e)) return;
    console.error(e);
    taskProgress.fail(e instanceof Error ? e.message : "未知错误");
    status(`处理未完成：${e instanceof Error ? e.message : "未知错误"}`);
  } finally {
    setTranscriptionBusy(false);
  }
});
function sync() {
  bpm.value = String(analysis.bpm);
  meter.value = `${analysis.meter}/${analysis.meterDenominator}`;
  key.value = String(analysis.keyPitchClass);
  mode.value = analysis.mode;
  $("#bpmConfidence").textContent = conf(analysis.confidence.bpm);
  $("#meterConfidence").textContent = conf(analysis.confidence.meter);
  $("#keyConfidence").textContent = conf(analysis.confidence.key);
  if (!serverProject && tempoMap.length === 1) tempoMap[0].bpm = analysis.bpm;
  renderTempoMap();
}
function renderTempoMap() {
  $("#tempo-map-list").innerHTML = tempoMap
    .map(
      (point, index) =>
        `<div class="tempo-point"><label>时间 ms<input data-tempo-time="${index}" type="number" min="0" step="100" value="${point.time_ms}" ${index === 0 ? "disabled" : ""}></label><label>BPM<input data-tempo-bpm="${index}" type="number" min="20" max="300" step="0.1" value="${point.bpm}"></label>${index === 0 ? "<span class=tempo-origin>起点</span>" : `<button data-remove-tempo="${index}" type="button" title="删除变速点" aria-label="删除变速点">×</button>`}</div>`,
    )
    .join("");
}
function readTempoMap(): Array<{ time_ms: number; bpm: number }> | null {
  const points = tempoMap.map((point, index) => ({
    time_ms:
      index === 0
        ? 0
        : Number($<HTMLInputElement>(`[data-tempo-time="${index}"]`).value),
    bpm: Number($<HTMLInputElement>(`[data-tempo-bpm="${index}"]`).value),
  }));
  if (
    points.some(
      (point, index) =>
        !Number.isFinite(point.time_ms) ||
        !Number.isFinite(point.bpm) ||
        point.time_ms < 0 ||
        point.bpm < 20 ||
        point.bpm > 300 ||
        (index > 0 && point.time_ms <= points[index - 1].time_ms),
    )
  )
    return null;
  return points;
}
function applyTempoMapFromControls() {
  const next = readTempoMap();
  if (!next) {
    $("#tempo-map-result").textContent = "变速点必须按时间递增，BPM 范围为 20–300";
    return false;
  }
  tempoMap = next;
  analysis.bpm = tempoMap[0].bpm;
  bpm.value = String(analysis.bpm);
  return true;
}
function syncQuantization(project: ApiScoreProject | null) {
  const settings = project?.quantization;
  $<HTMLInputElement>("#quantize-enabled").checked = settings?.enabled ?? true;
  $<HTMLSelectElement>("#quantize-grid").value = String(settings?.grid ?? 0.25);
  $<HTMLInputElement>("#quantize-strength").value = String(
    Math.round((settings?.strength ?? 1) * 100),
  );
  $("#quantize-strength-value").textContent =
    `${$<HTMLInputElement>("#quantize-strength").value}%`;
  $<HTMLInputElement>("#quantize-offset").value = String(settings?.offset_ms ?? 0);
  $<HTMLButtonElement>("#apply-quantization").disabled = !project;
  $("#quantization-result").textContent = settings?.conflicts.length
    ? `${settings.conflicts.length} 处同起点冲突已保留`
    : project
      ? "无同起点冲突"
      : "";
}
function melodyOptions() {
  const low = $<HTMLInputElement>("#melody-low"),
    high = $<HTMLInputElement>("#melody-high");
  if (
    !low.checkValidity() ||
    !high.checkValidity() ||
    !low.value ||
    !high.value ||
    Number(low.value) > Number(high.value)
  )
    throw new Error("请设置有效音域，最低音不能高于最高音");
  return {
    mode: $<HTMLSelectElement>("#melody-mode").value as
      "raw" | "balanced" | "conservative",
    low_pitch: Number(low.value),
    high_pitch: Number(high.value),
  };
}
function applyLocalRefinement() {
  const options = melodyOptions();
  rawNotes = refineLocalMelody(localOriginalNotes, options);
  const beat = 60 / analysis.bpm;
  let updated: EditableNote[] = rawNotes.map((n) => ({
    id: crypto.randomUUID(),
    source_start_ms: Math.round(n.startTimeSeconds * 1000),
    source_end_ms: Math.round((n.startTimeSeconds + n.durationSeconds) * 1000),
    pitch_midi: n.pitchMidi,
    confidence: n.amplitude,
    quantized_start: Math.round((n.startTimeSeconds / beat) * 4) / 4,
    quantized_duration: Math.max(
      0.25,
      Math.round(((n.startTimeSeconds + n.durationSeconds) / beat) * 4) / 4 -
        Math.round((n.startTimeSeconds / beat) * 4) / 4,
    ),
    origin: "model",
  }));
  if (options.mode !== "raw") {
    const starts = new Map<number, EditableNote>();
    for (const n of updated) {
      const previous = starts.get(n.quantized_start);
      if (!previous || n.confidence > previous.confidence)
        starts.set(n.quantized_start, n);
    }
    updated = [...starts.values()].sort(
      (a, b) => a.quantized_start - b.quantized_start,
    );
    updated.forEach((n, i) => {
      const next = updated[i + 1];
      if (next)
        n.quantized_duration = Math.min(
          n.quantized_duration,
          next.quantized_start - n.quantized_start,
        );
    });
  }
  scoreHistory = new ScoreHistory(updated);
  selectedNoteIndex = null;
  $("#melody-result").textContent =
    `${localOriginalNotes.length} → ${updated.length} 个音符`;
}
$("#refine-melody").addEventListener("click", async () => {
  if (
    transcriptionBusy ||
    editSaving ||
    (!notes.length &&
      !localOriginalNotes.length &&
      !serverProject?.raw_notes?.length)
  )
    return;
  if (
    scoreHistory?.canUndo &&
    !confirm("重新整理会替换当前音符编辑，是否继续？")
  )
    return;
  try {
    const options = melodyOptions();
    stop();
    editSaving = true;
    refreshSelection();
    $<HTMLButtonElement>("#refine-melody").disabled = true;
    if (serverProject) {
      serverProject = await api.refineMelody(
        serverProject.project_id,
        serverProject.revision,
        options,
      );
      applyApiProject(serverProject);
      $("#melody-result").textContent =
        `${serverProject.raw_notes?.length ?? 0} → ${serverProject.notes.length} 个音符`;
    } else applyLocalRefinement();
    await render();
    status(options.mode === "raw" ? "已恢复原始识别" : "主旋律整理已完成");
  } catch (error) {
    if (!(await recoverRevisionConflict(error)))
      status(
        `整理失败：${error instanceof Error ? error.message : "未知错误"}`,
      );
  } finally {
    editSaving = false;
    refreshSelection();
    $<HTMLButtonElement>("#refine-melody").disabled = false;
  }
});
async function update() {
  stop();
  if (document.activeElement === bpm)
    tempoMap[0].bpm = Number(bpm.value);
  else if (!applyTempoMapFromControls()) return;
  if (!bpm.checkValidity() || !Number.isFinite(Number(bpm.value))) {
    bpm.value = String(analysis.bpm);
    return;
  }
  const [numerator, denominator] = meter.value.split("/").map(Number);
  analysis = {
    ...analysis,
    bpm: Number(bpm.value),
    meter: numerator as 2 | 3 | 4 | 6,
    meterDenominator: denominator as 4 | 8,
    keyPitchClass: Number(key.value),
    mode: mode.value as "major" | "minor",
  };
  render();
  if (serverProject) {
    try {
      status("正在保存参数并重新量化…");
      serverProject = await api.requantizeProject(serverProject.project_id, {
        expected_revision: serverProject.revision,
        bpm: analysis.bpm,
        numerator: analysis.meter,
        denominator: analysis.meterDenominator,
        tonic: analysis.keyPitchClass,
        mode: analysis.mode,
        enabled: $<HTMLInputElement>("#quantize-enabled").checked,
        grid: Number($<HTMLSelectElement>("#quantize-grid").value),
        strength: Number($<HTMLInputElement>("#quantize-strength").value) / 100,
        offset_ms: Number($<HTMLInputElement>("#quantize-offset").value),
        tempo_map: tempoMap,
      });
      applyApiProject(serverProject);
      render();
      status(`已保存 · 修订 ${serverProject.revision}`);
    } catch (error) {
      status(
        `保存失败：${error instanceof Error ? error.message : "未知错误"}`,
      );
    }
  }
}
[bpm, meter, key, mode].forEach((el) => el.addEventListener("change", update));
$("#add-tempo-point").addEventListener("click", () => {
  if (!applyTempoMapFromControls()) return;
  const last = tempoMap.at(-1) ?? { time_ms: 0, bpm: analysis.bpm };
  tempoMap.push({ time_ms: last.time_ms + 10_000, bpm: last.bpm });
  renderTempoMap();
  $("#tempo-map-result").textContent = "已添加变速点，点击应用变速保存";
});
$("#tempo-map-list").addEventListener("click", (event) => {
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
    "[data-remove-tempo]",
  );
  if (!button) return;
  const index = Number(button.dataset.removeTempo);
  if (index > 0) {
    tempoMap.splice(index, 1);
    renderTempoMap();
    $("#tempo-map-result").textContent = "已删除变速点，点击应用变速保存";
  }
});
$("#apply-tempo-map").addEventListener("click", () => {
  if (!applyTempoMapFromControls()) return;
  void update();
});
$<HTMLInputElement>("#quantize-strength").addEventListener("input", () => {
  $("#quantize-strength-value").textContent =
    `${$<HTMLInputElement>("#quantize-strength").value}%`;
});
$("#apply-quantization").addEventListener("click", () => void update());
$("#example").addEventListener("click", () => {
  stop();
  scoreHistory = null;
  selectedNoteIndex = null;
  taskProgress.reset();
  serverProject = null;
  syncQuantization(null);
  clearF0Evidence();
  rawNotes = demoNotes();
  localOriginalNotes = rawNotes.map((n) => ({ ...n }));
  $("#melody-result").textContent = "";
  $<HTMLSelectElement>("#recent-project").value = "";
  $("#project-picker").textContent = "项目 / 谱面";
  $<HTMLButtonElement>("#delete-project").disabled = true;
  analysis = {
    bpm: 120,
    meter: 4,
    meterDenominator: 4,
    keyPitchClass: 0,
    mode: "major",
    confidence: { bpm: 0.92, meter: 0.81, key: 0.95 },
  };
  tempoMap = [{ time_ms: 0, bpm: analysis.bpm }];
  sync();
  render();
  status("已载入完整示例 · 所有参数均可修改");
});
let renderVersion = 0;
let rollZoom = 1;
async function render() {
  const version = ++renderVersion;
  renderBoundaryReview();
  const authoritativeNotes = scoreHistory?.value ?? serverProject?.notes;
  notes = authoritativeNotes
    ? displayQuantizedNotes(
        authoritativeNotes,
        analysis.bpm,
        keyRootMidi(analysis.keyPitchClass),
        analysis.mode,
      )
    : cleanAndQuantize(
        rawNotes,
        analysis.bpm,
        keyRootMidi(analysis.keyPitchClass),
        analysis.mode,
      );
  $<HTMLButtonElement>("#refine-melody").disabled =
    transcriptionBusy ||
    editSaving ||
    (!notes.length &&
      !localOriginalNotes.length &&
      !serverProject?.raw_notes?.length);
  if (!scoreHistory) {
    scoreHistory = new ScoreHistory(
      notes.map((n) => ({
        id: crypto.randomUUID(),
        source_start_ms: Math.round(n.startTimeSeconds * 1000),
        source_end_ms: Math.round(
          (n.startTimeSeconds + n.durationSeconds) * 1000,
        ),
        pitch_midi: n.pitchMidi,
        confidence: n.amplitude,
        quantized_start: n.startBeat,
        quantized_duration: n.durationBeats,
        origin: "model" as const,
      })),
    );
  }
  $("#empty").classList.toggle("hidden", notes.length > 0);
  const abcKey =
    KEYS[analysis.keyPitchClass].replace("♯", "#").replace("♭", "b") +
    (analysis.mode === "minor" ? "m" : "");
  const { default: ABCJS } = await import("abcjs");
  if (version !== renderVersion) return;
  const score = mappedAbc(
    notes,
    analysis.bpm,
    analysis.meter,
    analysis.meterDenominator,
    abcKey,
  );
  const [tune] = ABCJS.renderAbc("staff", score.abc, {
    responsive: "resize",
    add_classes: true,
    staffwidth: 860,
    wrap: {
      minSpacing: 1.7,
      maxSpacing: 2.7,
      preferredMeasuresPerLine: analysis.meter === 3 ? 6 : 4,
    },
  });
  for (const { offset, index } of score.mapping) {
    const item = tune?.getElementFromChar(offset) as {
      abselem?: import("abcjs").AbsoluteElement;
    } | null;
    const elements = item?.abselem?.elemset;
    for (const element of elements ?? []) {
      element.dataset.note = String(index);
      element.setAttribute("tabindex", "0");
      element.setAttribute("role", "button");
      element.setAttribute("aria-label", `音符 ${index + 1}`);
    }
  }
  for (const { offset, start, end } of score.restMapping) {
    const item = tune?.getElementFromChar(offset) as {
      abselem?: import("abcjs").AbsoluteElement;
    } | null;
    for (const element of item?.abselem?.elemset ?? []) {
      element.dataset.restStart = String(start);
      element.dataset.restEnd = String(end);
      element.setAttribute("aria-label", "休止符");
    }
  }
  $("#jianpu").innerHTML =
    `<div class="jianpu-meta">1 = ${KEYS[analysis.keyPitchClass]}　${analysis.meter}/${analysis.meterDenominator}　♩ = ${analysis.bpm}</div>` +
    renderJianpu(notes, (analysis.meter * 4) / analysis.meterDenominator);
  const evidenceProject =
    serverProject?.project_id === f0ProjectId ? serverProject : null;
  const boundaryMarkers = evidenceProject
    ? reviewableBoundarySuggestions(
        evidenceProject.transcription_evidence?.boundary_suggestions ?? [],
        evidenceProject.notes,
      )
        .map((suggestion) => ({
          suggestion,
          noteIndex: evidenceProject.notes.findIndex((note) =>
            note.source_note_ids?.includes(suggestion.source_note_id),
          ),
        }))
        .filter((item) => item.noteIndex >= 0)
        .map(({ suggestion, noteIndex }) => ({
          noteIndex,
          originalEndSeconds: suggestion.original_end_ms / 1000,
          proposedEndSeconds: suggestion.proposed_end_ms / 1000,
          status: suggestion.review_status,
        }))
    : [];
  const performanceNotes = (serverProject?.performance_notes ?? []).map((note) => ({
    startSeconds: note.source_start_ms / 1000,
    endSeconds: note.source_end_ms / 1000,
    pitchMidi: note.pitch_midi,
  }));
  const conflictIds = new Set(
    serverProject?.quantization?.conflicts.flatMap((conflict) => conflict.note_ids) ?? [],
  );
  const conflictNoteIndices = serverProject
    ? serverProject.notes.flatMap((note, index) =>
        conflictIds.has(note.id) ? [index] : [],
      )
    : [];
  $("#piano").innerHTML = renderPianoRoll(
    notes,
    selectedNoteIndex,
    900,
    280,
    serverProject || evidenceProject
      ? {
          bpm: analysis.bpm,
          frames: $<HTMLInputElement>("#show-f0").checked ? f0Frames : [],
          boundaries: boundaryMarkers,
          performanceNotes,
          conflictNoteIndices,
        }
      : undefined,
  );
  applyRollZoom();
  refreshSelection();
  [play, $<HTMLButtonElement>("#midi"), $<HTMLButtonElement>("#xml")].forEach(
    (b) => (b.disabled = !notes.length),
  );
  $<HTMLSelectElement>("#midi-version").disabled = !notes.length;
  $<HTMLSelectElement>("#playback-version").disabled = !notes.length;
}
$("#boundary-review").addEventListener("click", async (event) => {
  const button = (event.target as Element).closest<HTMLButtonElement>("button");
  if (!button || !serverProject || editSaving || transcriptionBusy) return;
  const sourceId = button.dataset.boundaryLocate;
  if (sourceId) {
    const decodedSourceId = decodeURIComponent(sourceId);
    const index = serverProject.notes.findIndex((note) =>
      note.source_note_ids?.includes(decodedSourceId),
    );
    if (index >= 0) {
      selectedNoteIndex = index;
      refreshSelection();
      activateView("piano");
    }
    const suggestion =
      serverProject.transcription_evidence?.boundary_suggestions.find(
        (item) => item.source_note_id === decodedSourceId,
      );
    if (suggestion) {
      audio.currentTime = Math.max(0, suggestion.original_end_ms / 1000 - 0.6);
      void audio.play();
    }
    return;
  }
  const suggestionId = button.dataset.suggestionId;
  const action = button.dataset.boundaryAction as
    "accept" | "reject" | "reset" | undefined;
  if (!suggestionId || !action) return;
  editSaving = true;
  renderBoundaryReview();
  try {
    status(action === "accept" ? "正在采用止音建议…" : "正在保存审阅结果…");
    serverProject = await api.reviewBoundarySuggestion(
      serverProject.project_id,
      decodeURIComponent(suggestionId),
      { expected_revision: serverProject.revision, action },
    );
    applyApiProject(serverProject);
    await render();
    status(`止音建议已更新 · 修订 ${serverProject.revision}`);
  } catch (error) {
    if (!(await recoverRevisionConflict(error)))
      status(
        `审阅失败：${error instanceof Error ? error.message : "未知错误"}`,
      );
  } finally {
    editSaving = false;
    renderBoundaryReview();
    refreshSelection();
  }
});
function refreshSelection() {
  editableSelectionId =
    selectedNoteIndex === null
      ? undefined
      : scoreHistory?.value[selectedNoteIndex]?.id;
  document
    .querySelectorAll<HTMLElement | SVGElement>("[data-note]")
    .forEach((el) => {
      const selected = Number(el.dataset.note) === selectedNoteIndex;
      el.classList.toggle("selected", selected);
      el.setAttribute("aria-pressed", String(selected));
    });
  const selected =
    selectedNoteIndex !== null && Boolean(notes[selectedNoteIndex]);
  [
    "#pitch-up",
    "#pitch-down",
    "#move-earlier",
    "#move-later",
    "#shorter",
    "#longer",
    "#split",
    "#merge",
    "#delete-note",
  ].forEach(
    (selector) =>
      ($<HTMLButtonElement>(selector).disabled =
        !selected || !scoreHistory || editSaving),
  );
  $<HTMLButtonElement>("#undo").disabled = !scoreHistory?.canUndo || editSaving;
  $<HTMLButtonElement>("#redo").disabled = !scoreHistory?.canRedo || editSaving;
  [bpm, meter, key, mode].forEach((el) => {
    el.disabled = editSaving;
  });
  for (const selector of [
    "#example",
    "#recent-project",
    "#file",
    "#delete-project",
    "#transcribe",
  ]) {
    const el = $<HTMLButtonElement>(selector);
    if (editSaving) {
      if (!el.hasAttribute("data-save-disabled"))
        el.dataset.saveDisabled = String(el.disabled);
      el.disabled = true;
    } else if (el.hasAttribute("data-save-disabled")) {
      el.disabled = el.dataset.saveDisabled === "true";
      delete el.dataset.saveDisabled;
    }
  }
}
for (const selector of ["#staff", "#jianpu", "#piano"]) {
  $(selector).addEventListener("click", (event) => {
    const target = (event.target as Element).closest<HTMLElement | SVGElement>(
      "[data-note]",
    );
    if (!target) return;
    selectedNoteIndex = Number(target.dataset.note);
    refreshSelection();
    document
      .querySelectorAll(`[data-note="${selectedNoteIndex}"]`)
      .forEach((el) => {
        el.classList.remove("note-hit");
        void el.getBoundingClientRect();
        el.classList.add("note-hit");
      });
    target.focus();
  });
}
function applyRollZoom() {
  const svg = $("#piano").querySelector("svg");
  if (svg) {
    svg.style.width = `${rollZoom * 100}%`;
    svg.style.height = "280px";
    svg.setAttribute("preserveAspectRatio", "none");
  }
  $<HTMLInputElement>("#zoom").value = String(rollZoom);
  $("#zoom-value").textContent = `${Math.round(rollZoom * 100)}%`;
}
function zoomRoll(next: number, anchor: number) {
  const pane = $("#piano");
  const oldWidth =
    pane.querySelector("svg")?.getBoundingClientRect().width ??
    pane.clientWidth;
  const position = (pane.scrollLeft + anchor) / oldWidth;
  rollZoom = Math.max(1, Math.min(8, next));
  applyRollZoom();
  pane.scrollLeft =
    position *
      (pane.querySelector("svg")?.getBoundingClientRect().width ?? oldWidth) -
    anchor;
}
$("#piano").addEventListener(
  "wheel",
  (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    const delta =
      event.deltaY *
      (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 280 : 1);
    zoomRoll(
      rollZoom * Math.exp(-delta * 0.002),
      event.clientX - $("#piano").getBoundingClientRect().left,
    );
  },
  { passive: false },
);
$("#zoom").addEventListener("input", () =>
  zoomRoll(
    Number($<HTMLInputElement>("#zoom").value),
    $("#piano").clientWidth / 2,
  ),
);
let rollDrag: { index: number; resize: boolean; x: number; y: number } | null =
  null;
function scoreEditStep() {
  const step = Number($<HTMLSelectElement>("#quantize-grid").value);
  return Number.isFinite(step) && step > 0 ? step : 0.25;
}
$<HTMLDivElement>("#piano").addEventListener("pointerdown", (event) => {
  const target = (event.target as Element).closest<SVGElement>("[data-note]");
  if (!target) return;
  rollDrag = {
    index: Number(target.dataset.note),
    resize: event.shiftKey,
    x: event.clientX,
    y: event.clientY,
  };
  selectedNoteIndex = rollDrag.index;
  $("#piano").setPointerCapture(event.pointerId);
  refreshSelection();
});
$("#piano").addEventListener("pointercancel", () => {
  rollDrag = null;
});
$<HTMLDivElement>("#piano").addEventListener("pointerup", (event) => {
  const drag = rollDrag;
  rollDrag = null;
  if (!drag || !scoreHistory || editSaving) return;
  if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 4) return;
  const svg = $<HTMLDivElement>("#piano").querySelector("svg");
  const note = scoreHistory.value[drag.index];
  if (!svg || !note) return;
  const bounds = svg.getBoundingClientRect();
  const x = (event.clientX - drag.x) / bounds.width;
  const y = (event.clientY - drag.y) / bounds.height;
  const metrics = pianoRollMetrics(notes);
  const step = scoreEditStep();
  if (drag.resize) {
    const duration =
      Math.round((note.quantized_duration + x * metrics.endBeat) / step) * step;
    void saveEditedNotes(
      scoreHistory.execute({
        type: "resize",
        noteId: note.id,
        duration,
      }),
      "时值拖动",
    );
  } else {
    const start =
      Math.round((note.quantized_start + x * metrics.endBeat) / step) * step;
    const pitch = Math.round(
      note.pitch_midi - y * (metrics.highPitch - metrics.lowPitch + 1),
    );
    void saveEditedNotes(
      scoreHistory.execute({ type: "move", noteId: note.id, start, pitch }),
      "音符拖动",
    );
  }
});
async function transposeSelected(semitones: number) {
  const current = selectedEditableNote();
  if (!current || !scoreHistory) return;
  const updated = scoreHistory.execute({
    type: "move",
    noteId: current.id,
    start: current.quantized_start,
    pitch: current.pitch_midi + semitones,
  });
  await saveEditedNotes(updated, "音高校正");
}
async function moveSelected(delta: number) {
  const current = selectedEditableNote();
  if (!current || !scoreHistory) return;
  const start = Math.max(0, current.quantized_start + delta);
  if (start === current.quantized_start) return;
  await saveEditedNotes(
    scoreHistory.execute({
      type: "move",
      noteId: current.id,
      start,
      pitch: current.pitch_midi,
    }),
    delta < 0 ? "提前起音" : "延后起音",
  );
}
function useEditedNotes(updated: EditableNote[]) {
  const secondsPerBeat = 60 / analysis.bpm;
  rawNotes = updated.map((note) => ({
    pitchMidi: note.pitch_midi,
    amplitude: note.confidence,
    startTimeSeconds: note.quantized_start * secondsPerBeat,
    durationSeconds: note.quantized_duration * secondsPerBeat,
  }));
  if (selectedNoteIndex !== null && selectedNoteIndex >= updated.length) {
    selectedNoteIndex = updated.length ? updated.length - 1 : null;
  }
  render();
}
async function saveEditedNotes(updated: EditableNote[], label: string) {
  stop();
  const selectedId =
    selectedNoteIndex === null ? undefined : editableSelectionId;
  if (selectedId) {
    const index = updated.findIndex((n) => n.id === selectedId);
    if (index >= 0) selectedNoteIndex = index;
  }
  useEditedNotes(updated);
  if (!serverProject) {
    status(`${label}已更新`);
    return;
  }
  editSaving = true;
  refreshSelection();
  try {
    status(`正在保存${label}…`);
    serverProject = await api.updateProject(
      serverProject.project_id,
      serverProject.revision,
      updated,
    );
    renderBoundaryReview();
    status(`${label}已保存 · 修订 ${serverProject.revision}`);
  } catch (error) {
    if (await recoverRevisionConflict(error)) return;
    status(`保存失败：${error instanceof Error ? error.message : "未知错误"}`);
  } finally {
    editSaving = false;
    refreshSelection();
  }
}
let editSaving = false;
let editableSelectionId: string | undefined;
document.addEventListener("keydown", (event) => {
  if (
    (event.target as Element).closest(
      "input, select, textarea, [contenteditable=true]",
    )
  )
    return;
  if (
    ["Enter", " "].includes(event.key) &&
    (event.target as Element).closest("[data-note]")
  ) {
    event.preventDefault();
    (event.target as HTMLElement).dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
    return;
  }
  if (
    selectedNoteIndex === null ||
    !["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)
  )
    return;
  event.preventDefault();
  if (event.key === "ArrowUp" || event.key === "ArrowDown") {
    void transposeSelected(event.key === "ArrowUp" ? 1 : -1);
  } else {
    void moveSelected(
      (event.key === "ArrowLeft" ? -1 : 1) * scoreEditStep(),
    );
  }
});
function selectedEditableNote() {
  return selectedNoteIndex === null || editSaving
    ? undefined
    : scoreHistory?.value[selectedNoteIndex];
}
$("#pitch-up").addEventListener("click", () => void transposeSelected(1));
$("#pitch-down").addEventListener("click", () => void transposeSelected(-1));
$("#move-earlier").addEventListener("click", () =>
  void moveSelected(-scoreEditStep()),
);
$("#move-later").addEventListener("click", () =>
  void moveSelected(scoreEditStep()),
);
$("#delete-note").addEventListener("click", () => {
  const note = selectedEditableNote();
  if (note && scoreHistory)
    void saveEditedNotes(
      scoreHistory.execute({ type: "delete", noteId: note.id }),
      "删除",
    );
});
$("#shorter").addEventListener("click", () => resizeSelected(-scoreEditStep()));
$("#longer").addEventListener("click", () => resizeSelected(scoreEditStep()));
function resizeSelected(delta: number) {
  const note = selectedEditableNote();
  if (note && scoreHistory)
    void saveEditedNotes(
      scoreHistory.execute({
        type: "resize",
        noteId: note.id,
        duration: note.quantized_duration + delta,
      }),
      delta > 0 ? "延长" : "缩短",
    );
}
$("#split").addEventListener("click", () => {
  const note = selectedEditableNote();
  if (note && scoreHistory)
    void saveEditedNotes(
      scoreHistory.execute({
        type: "split",
        noteId: note.id,
        at: note.quantized_start + note.quantized_duration / 2,
        rightId: crypto.randomUUID(),
      }),
      "拆分",
    );
});
$("#merge").addEventListener("click", () => {
  const note = selectedEditableNote();
  const right =
    selectedNoteIndex === null
      ? undefined
      : scoreHistory?.value[selectedNoteIndex + 1];
  if (note && right && scoreHistory)
    void saveEditedNotes(
      scoreHistory.execute({
        type: "merge",
        leftId: note.id,
        rightId: right.id,
      }),
      "合并",
    );
});
$("#undo").addEventListener("click", () => {
  if (scoreHistory && !editSaving)
    void saveEditedNotes(scoreHistory.undo(), "撤销");
});
$("#redo").addEventListener("click", () => {
  if (scoreHistory && !editSaving)
    void saveEditedNotes(scoreHistory.redo(), "重做");
});
function activateView(view: string) {
  document
    .querySelectorAll("[data-view]")
    .forEach((button) => button.classList.remove("active"));
  document.querySelector(`[data-view="${view}"]`)?.classList.add("active");
  $("#staff").classList.toggle("hidden", view !== "staff");
  $("#jianpu").classList.toggle("hidden", view !== "jianpu");
  $("#piano").classList.toggle("hidden", view !== "piano");
  $("#roll-zoom").classList.toggle("hidden", view !== "piano");
}
document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach((button) =>
  button.addEventListener("click", () =>
    activateView(button.dataset.view ?? "staff"),
  ),
);
$<HTMLInputElement>("#show-f0").addEventListener("change", () => void render());
function stop() {
  scorePlayer.stop();
  syncingAudio = false;
  syncedAudioRange = null;
  audio.pause();
  playing = false;
  play.textContent = "▶ 演奏";
  $("#playback-state").textContent = "";
  document
    .querySelectorAll(".playing, .playing-rest")
    .forEach((e) => e.classList.remove("playing", "playing-rest"));
}
play.addEventListener("click", async () => {
  if (playing) return stop();
  if (!notes.length) return;
  playing = true;
  play.textContent = "■ 停止";
  audio.pause();
  try {
    const performancePlayback =
      $<HTMLSelectElement>("#playback-version").value === "performance" &&
      Boolean(serverProject?.performance_notes?.length);
    const beatMs = 60_000 / analysis.bpm;
    const allPlaybackNotes = performancePlayback
      ? displayQuantizedNotes(
          (serverProject?.performance_notes ?? []).map((note) => ({
            pitch_midi: note.pitch_midi,
            confidence: note.confidence,
            quantized_start: note.source_start_ms / beatMs,
            quantized_duration: (note.source_end_ms - note.source_start_ms) / beatMs,
          })),
          analysis.bpm,
          keyRootMidi(analysis.keyPitchClass),
          analysis.mode,
        )
      : notes;
    const selected = selectedNoteIndex === null ? undefined : notes[selectedNoteIndex];
    const startFromSelected =
      $<HTMLSelectElement>("#playback-start").value === "selected" &&
      Boolean(selected);
    const clipStartSeconds = startFromSelected
      ? selected!.startBeat * beatMs / 1000
      : 0;
    const clipEndSeconds = Math.max(
      ...allPlaybackNotes.map(
        (note) => note.startTimeSeconds + note.durationSeconds,
      ),
      0,
    );
    const loopEnabled = $<HTMLInputElement>("#playback-loop").checked;
    const playbackRate = Number(
      $<HTMLSelectElement>("#playback-speed").value,
    );
    const playbackMode = $<HTMLSelectElement>("#playback-mode").value;
    const offsetSeconds = Number($<HTMLInputElement>("#audio-offset").value || 0) / 1000;
    const audioEnabled = playbackMode !== "score";
    const sourceEnabled = playbackMode === "source" || playbackMode === "mix-source";
    const vocalsEnabled = playbackMode === "vocals" || playbackMode === "mix-vocals";
    const scoreEnabled = playbackMode === "score" || playbackMode === "mix-source" || playbackMode === "mix-vocals";
    if (sourceEnabled) {
      audio.src = sourceAudioUrl || audio.src;
      audio.volume = Number($<HTMLInputElement>("#source-volume").value) / 100;
    } else if (vocalsEnabled) {
      audio.src = vocalsAudioUrl || audio.src;
      audio.volume = Number($<HTMLInputElement>("#vocal-volume").value) / 100;
    }
    const playbackEntries = allPlaybackNotes
      .map((note, index) => ({ note, index }))
      .filter(
        ({ note }) =>
          note.startTimeSeconds < clipEndSeconds &&
          note.startTimeSeconds + note.durationSeconds > clipStartSeconds,
      );
    const playbackNotes = playbackEntries.map(({ note }) => ({
      ...note,
      startTimeSeconds: Math.max(0, note.startTimeSeconds - clipStartSeconds),
      durationSeconds:
        Math.min(
          note.startTimeSeconds + note.durationSeconds,
          clipEndSeconds,
        ) - Math.max(note.startTimeSeconds, clipStartSeconds),
      startBeat:
        (Math.max(note.startTimeSeconds, clipStartSeconds) -
          clipStartSeconds) *
        (analysis.bpm / 60),
      durationBeats:
        (Math.min(
          note.startTimeSeconds + note.durationSeconds,
          clipEndSeconds,
        ) -
          Math.max(note.startTimeSeconds, clipStartSeconds)) *
        (analysis.bpm / 60),
    }));
    const performanceToScore = performancePlayback
      ? (serverProject?.performance_notes ?? []).map((performanceNote) =>
          serverProject?.notes.findIndex((note) => note.id === performanceNote.id),
        )
      : [];
    const elements = [
      ...document.querySelectorAll<HTMLElement | SVGElement>("[data-note]"),
    ];
    const restElements = [
      ...document.querySelectorAll<HTMLElement | SVGElement>(
        "[data-rest-start]",
      ),
    ];
    let previousActive = "";
    const playClip = async () => {
      if (!playing) return;
      await scorePlayer.play(
        playbackNotes,
        analysis.bpm * playbackRate,
        (indices, elapsedSeconds) => {
          const sourceIndices = indices.map(
            (index) => playbackEntries[index]?.index ?? -1,
          );
          const displayedIndices = performancePlayback
            ? sourceIndices
                .map((index) => performanceToScore[index] ?? -1)
                .filter((index) => index >= 0)
            : sourceIndices.filter((index) => index >= 0);
          const sourceBeat =
            (clipStartSeconds + elapsedSeconds * playbackRate) *
            (analysis.bpm / 60);
          const activeRestElements = restElements.filter(
            (element) =>
              Number(element.dataset.restStart) <= sourceBeat &&
              Number(element.dataset.restEnd) > sourceBeat,
          );
          const activeRest = activeRestElements[0];
          const key = `${displayedIndices.join(",")}|${activeRest?.dataset.restStart ?? ""}`;
          if (key === previousActive) return;
          previousActive = key;
          const active = new Set(displayedIndices);
          $("#playback-state").textContent = displayedIndices.length
            ? "正在演奏音符"
            : activeRest
              ? "正在演奏休止符"
              : "休止";
          elements.forEach((el) => {
            const hit = active.has(Number(el.dataset.note));
            if (hit && !el.classList.contains("playing")) {
              el.classList.remove("note-hit");
              void el.getBoundingClientRect();
              el.classList.add("note-hit");
            }
            el.classList.toggle("playing", hit);
          });
          restElements.forEach((element) =>
            element.classList.toggle(
              "playing-rest",
              activeRestElements.includes(element),
            ),
          );
        },
        () => {
          if (loopEnabled && playing) {
            void playClip();
          } else {
            stop();
          }
        },
        Number($<HTMLInputElement>("#score-volume").value) / 100,
      );
    };
    if (audioEnabled && sourceBuffer && clipEndSeconds > clipStartSeconds) {
      syncingAudio = true;
      syncedAudioRange = {
        start: Math.max(0, clipStartSeconds + offsetSeconds),
        end: Math.max(0, clipEndSeconds + offsetSeconds),
        loop: loopEnabled,
      };
      audio.currentTime = Math.max(0, Math.min(clipStartSeconds + offsetSeconds, audio.duration || clipStartSeconds + offsetSeconds));
      audio.playbackRate = playbackRate;
      audio.preservesPitch = true;
      await audio.play();
    }
    if (scoreEnabled) await playClip();
    else if (audioEnabled) {
      audio.addEventListener("ended", stop, { once: true });
    }
  } catch (error) {
    stop();
    status(`播放失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
});
audio.addEventListener("play", () => {
  if (!syncingAudio) stop();
});
audio.addEventListener("timeupdate", () => {
  if (!syncingAudio || !playing || !syncedAudioRange) return;
  if (audio.currentTime < syncedAudioRange.end) return;
  if (syncedAudioRange.loop) {
    audio.currentTime = syncedAudioRange.start;
  } else {
    stop();
  }
});
audio.addEventListener("ended", () => {
  if (syncingAudio && playing) stop();
});
for (const [id, output] of [["score-volume", "score-volume-value"], ["source-volume", "source-volume-value"], ["vocal-volume", "vocal-volume-value"]] as const) {
  $<HTMLInputElement>(`#${id}`).addEventListener("input", () => {
    const value = $<HTMLInputElement>(`#${id}`).value;
    $(`#${output}`).textContent = `${value}%`;
    localStorage.setItem(`vocal-score.${id}`, value);
    if (id === "source-volume" && audio.src === sourceAudioUrl) audio.volume = Number(value) / 100;
    if (id === "vocal-volume" && audio.src === vocalsAudioUrl) audio.volume = Number(value) / 100;
  });
  const saved = localStorage.getItem(`vocal-score.${id}`);
  if (saved) $<HTMLInputElement>(`#${id}`).value = saved;
}
const playbackPreferences = [
  ["playback-version", "vocal-score.playback-version"],
  ["playback-mode", "vocal-score.playback-mode"],
  ["playback-start", "vocal-score.playback-start"],
  ["playback-speed", "vocal-score.playback-speed"],
] as const;
for (const [id, storageKey] of playbackPreferences) {
  const control = $<HTMLSelectElement>(`#${id}`);
  const saved = localStorage.getItem(storageKey);
  if (saved && [...control.options].some((option) => option.value === saved))
    control.value = saved;
  control.addEventListener("change", () =>
    localStorage.setItem(storageKey, control.value),
  );
}
const loopControl = $<HTMLInputElement>("#playback-loop");
loopControl.checked = localStorage.getItem("vocal-score.playback-loop") === "true";
loopControl.addEventListener("change", () =>
  localStorage.setItem("vocal-score.playback-loop", String(loopControl.checked)),
);
$<HTMLInputElement>("#audio-offset").addEventListener("change", () => {
  const value = $<HTMLInputElement>("#audio-offset").value;
  localStorage.setItem("vocal-score.audio-offset", value);
  if (serverProject) {
    void api.updateAudioAlignment(serverProject.project_id, {
      expected_revision: serverProject.revision,
      offset_ms: Number(value),
      source: "manual",
      status: "confirmed",
    }).then((project) => {
      if (serverProject?.project_id === project.project_id) serverProject = project;
    }).catch((error: unknown) => status(`保存音频偏移失败：${error instanceof Error ? error.message : "未知错误"}`));
  }
});
$("#auto-align").addEventListener("click", async () => {
  if (!sourceBuffer || !notes.length) {
    status("需要先载入音频和谱面");
    return;
  }
  const onsets = detectEnergyOnsets(sourceBuffer.getChannelData(0), sourceBuffer.sampleRate);
  const result = estimateGlobalOffset(notes.map((note) => note.startTimeSeconds), onsets);
  const offsetMs = Math.round(result.offsetSeconds * 1000);
  $<HTMLInputElement>("#audio-offset").value = String(offsetMs);
  $("#alignment-result").textContent = result.confidence >= 0.5
    ? `候选 ${offsetMs} ms · ${result.matchedCount} 个起音匹配`
    : "证据不足，建议手动调整";
  $<HTMLInputElement>("#audio-offset").dispatchEvent(new Event("change"));
  status(result.confidence >= 0.5 ? "已应用自动对齐候选，可继续手动微调" : "自动对齐置信度较低，已保留候选值");
});
const savedAudioOffset = localStorage.getItem("vocal-score.audio-offset");
if (savedAudioOffset) $<HTMLInputElement>("#audio-offset").value = savedAudioOffset;
window.addEventListener("pagehide", stop);
function midiVersion() {
  return $<HTMLSelectElement>("#midi-version").value as
    | "score"
    | "performance";
}
function downloadServerExport(
  format: "midi" | "musicxml",
  version: "score" | "performance" = "score",
) {
  if (!serverProject) return false;
  const link = document.createElement("a");
  link.href = api.exportUrl(serverProject.project_id, format, version);
  link.download = "";
  link.click();
  return true;
}
$("#midi").addEventListener("click", () => {
  const version = midiVersion();
  if (!downloadServerExport("midi", version))
    void import("./export").then(({ exportMidi }) =>
      exportMidi(notes, analysis, version),
    );
});
$("#xml").addEventListener("click", () => {
  if (!downloadServerExport("musicxml"))
    void import("./export").then(({ exportMusicXml }) =>
      exportMusicXml(notes, analysis),
    );
});
$<HTMLButtonElement>("#retry-job").disabled =
  !localStorage.getItem(FAILED_JOB_KEY);
void refreshProjects();
void resumeActiveJob();
