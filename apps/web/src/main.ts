import ABCJS from "abcjs";
import {
  JOB_STAGE_LABELS,
  type ScoreProject as ApiScoreProject,
} from "@vocal-score/contracts";
import { VocalScoreApi } from "@vocal-score/contracts/client";
import { ScoreHistory, type EditableNote } from "@vocal-score/score-core";
import {
  BasicPitch,
  addPitchBendsToNoteEvents,
  noteFramesToTime,
  outputToNotesPoly,
} from "@spotify/basic-pitch";
import { analyzeMusic } from "./analysis";
import { exportMidi, exportMusicXml, keyName, keyRootMidi } from "./export";
import { cleanAndQuantize, demoNotes, toAbc } from "./music";
import { renderPianoRoll } from "./piano-roll";
import { isolateCenterVocal, resampleAudio } from "./separation";
import type { MusicalAnalysis, RawNote, ScoreNote } from "./types";
import "./style.css";
import "./editor.css";

const KEYS = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
const api = new VocalScoreApi();
const ACTIVE_JOB_KEY = "vocal-score.active-job";
const FAILED_JOB_KEY = "vocal-score.failed-job";
document.querySelector<HTMLDivElement>("#app")!.innerHTML =
  `<main><header><div><span class="eyebrow">VOCAL SCORE STUDIO</span><h1>拾音</h1></div><p>从一首歌里分离人声，自动识别速度、拍号与调性，生成可演奏的简谱和五线谱。</p></header><section class="workbench"><aside><label class="drop" id="drop"><input id="file" type="file" accept="audio/*"><span class="drop-icon">↥</span><strong>放入歌曲或人声</strong><small>MP3 · WAV · OGG · FLAC</small></label><audio id="audio" controls></audio><div class="field"><label>人声分离 <output id="isolateValue">82%</output></label><input id="isolate" type="range" min="0" max="100" value="82"><small>适合主唱居中的立体声歌曲</small></div><div class="field"><label>识别灵敏度</label><select id="sensitivity"><option value="0.35">均衡</option><option value="0.48">保守</option><option value="0.25">灵敏</option></select></div><button class="primary" id="transcribe" disabled>自动分析并扒谱</button><button class="ghost" id="example">载入完整示例</button><div class="progress"><i id="progress"></i></div><p class="status" id="status">等待音频</p></aside><article><section class="analysis-panel"><div><span>速度 BPM</span><input id="bpm" type="number" min="40" max="240" value="120"><small id="bpmConfidence">待分析</small></div><div><span>拍号</span><select id="meter"><option value="4">4 / 4</option><option value="3">3 / 4</option></select><small id="meterConfidence">待分析</small></div><div><span>调性</span><section><select id="key">${KEYS.map((k, i) => `<option value="${i}">${k}</option>`).join("")}</select><select id="mode"><option value="major">大调</option><option value="minor">小调</option></select></section><small id="keyConfidence">待分析</small></div></section><div class="toolbar"><div class="tabs"><button class="active" data-view="staff">五线谱</button><button data-view="jianpu">简谱</button></div><div class="actions"><button id="play" disabled>▶ 演奏</button><button id="midi" disabled>导出 MIDI</button><button id="xml" disabled>导出 MusicXML</button></div></div><div id="staff" class="score"></div><div id="jianpu" class="score hidden"></div><div class="empty" id="empty"><div>♪</div><strong>完整乐谱会出现在这里</strong><span>导入歌曲后，一次完成分离、分析与转谱</span></div></article></section><footer>本地处理 · 不上传音频 · 自动识别结果可手动修正</footer></main>`;
document.querySelector(".toolbar")!.insertAdjacentHTML(
  "afterend",
  `<div class="edit-actions"><button id="undo" disabled>↶ 撤销</button><button id="redo" disabled>↷ 重做</button><button id="shorter" disabled>缩短</button><button id="longer" disabled>延长</button><button id="split" disabled>拆分</button><button id="merge" disabled>与后音合并</button><button id="delete-note" disabled>删除</button></div>`,
);
document.querySelector(".tabs")!.insertAdjacentHTML(
  "beforeend",
  `<button data-view="piano">钢琴卷帘</button>`,
);
document.querySelector("#staff")!.insertAdjacentHTML(
  "beforebegin",
  `<div id="piano" class="score piano-roll hidden"></div>`,
);

const $ = <T extends HTMLElement>(s: string) => document.querySelector<T>(s)!;
const input = $<HTMLInputElement>("#file"),
  audio = $<HTMLAudioElement>("#audio"),
  transcribe = $<HTMLButtonElement>("#transcribe"),
  bpm = $<HTMLInputElement>("#bpm"),
  meter = $<HTMLSelectElement>("#meter"),
  key = $<HTMLSelectElement>("#key"),
  mode = $<HTMLSelectElement>("#mode"),
  play = $<HTMLButtonElement>("#play");
transcribe.insertAdjacentHTML(
  "afterend",
  `<button class="ghost" id="retry-job" disabled>重试上次失败任务</button>`,
);
audio.insertAdjacentHTML(
  "afterend",
  `<div class="field"><label>处理引擎</label><select id="engine"><option value="server-high">后端高质量 · Demucs</option><option value="server-demo">后端演示 · 快速</option><option value="local">浏览器本地模式</option></select><small>高质量模式需要部署模型 Worker</small></div>`,
);
document.querySelector("aside")!.insertAdjacentHTML(
  "afterbegin",
  `<div class="recent-projects"><label for="recent-project">最近项目</label><div><select id="recent-project"><option value="">选择已保存项目…</option></select><button id="refresh-projects" title="刷新项目">↻</button><button id="delete-project" title="删除项目" disabled>删除</button></div></div>`,
);
let sourceBuffer: AudioBuffer | null = null,
  sourceFile: File | null = null,
  serverProject: ApiScoreProject | null = null,
  rawNotes: RawNote[] = [],
  notes: ScoreNote[] = [];
let selectedNoteIndex: number | null = null;
let scoreHistory: ScoreHistory | null = null;
let analysis: MusicalAnalysis = {
  bpm: 120,
  meter: 4,
  keyPitchClass: 0,
  mode: "major",
  confidence: { bpm: 0, meter: 0, key: 0 },
};
let timers: number[] = [],
  playing = false;
function status(message: string, pct?: number) {
  $("#status").textContent = message;
  if (pct !== undefined) $("#progress").style.width = `${pct}%`;
}
const conf = (v: number) =>
  v < 0.4 ? "低置信度 · 建议校正" : v < 0.7 ? "中等置信度" : "高置信度";
async function load(file: File) {
  status("正在解码音频…", 3);
  sourceFile = file;
  serverProject = null;
  audio.src = URL.createObjectURL(file);
  sourceBuffer = await new AudioContext().decodeAudioData(
    await file.arrayBuffer(),
  );
  transcribe.disabled = false;
  status(`已载入 ${file.name} · ${sourceBuffer.duration.toFixed(1)} 秒`, 0);
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
isolate.addEventListener(
  "input",
  () => ($("#isolateValue").textContent = `${isolate.value}%`),
);
async function infer(buffer: AudioBuffer) {
  const frames: number[][] = [],
    onsets: number[][] = [],
    contours: number[][] = [];
  const model = new BasicPitch(
    `${location.origin}/basic-pitch-model/model.json`,
  );
  await model.evaluateModel(
    buffer,
    (f, o, c) => {
      frames.push(...f);
      onsets.push(...o);
      contours.push(...c);
    },
    (p) => status(`正在识别人声旋律… ${Math.round(p * 100)}%`, 20 + p * 65),
  );
  const threshold = Number($<HTMLSelectElement>("#sensitivity").value);
  return noteFramesToTime(
    addPitchBendsToNoteEvents(
      contours,
      outputToNotesPoly(frames, onsets, threshold, 0.28, 5),
    ),
  ) as RawNote[];
}
async function runLocal() {
  if (!sourceBuffer) return;
  status("正在提取中心人声与增强语音频段…", 8);
  const isolated = await isolateCenterVocal(
    sourceBuffer,
    Number(isolate.value) / 100,
  );
  status("正在重采样人声…", 15);
  const vocal = await resampleAudio(isolated);
  status("正在加载音高模型…", 18);
  rawNotes = await infer(vocal);
  status("正在分析 BPM、拍号与调性…", 90);
  analysis = analyzeMusic(sourceBuffer, rawNotes);
}
function applyApiProject(project: ApiScoreProject) {
  selectedNoteIndex = null;
  scoreHistory = new ScoreHistory(project.notes);
  const tempo = project.analysis.tempo_map[0];
  const meterPoint = project.analysis.meter_map[0];
  const keyPoint = project.analysis.key_map[0];
  rawNotes = project.notes.map((note) => ({
    pitchMidi: note.pitch_midi,
    amplitude: note.confidence,
    startTimeSeconds: note.source_start_ms / 1000,
    durationSeconds: (note.source_end_ms - note.source_start_ms) / 1000,
  }));
  analysis = {
    bpm: tempo?.bpm ?? 120,
    meter: meterPoint?.numerator === 3 ? 3 : 4,
    keyPitchClass: keyPoint?.tonic ?? 0,
    mode: keyPoint?.mode ?? "major",
    confidence: {
      bpm: project.analysis.confidence.tempo ?? 0,
      meter: project.analysis.confidence.meter ?? 0,
      key: project.analysis.confidence.key ?? 0,
    },
  };
}
async function runServer(quality: "demo" | "high") {
  if (!sourceFile) return;
  status("正在上传音频…", 3);
  const upload = await api.upload(sourceFile);
  status("已进入后端处理队列…", 6);
  const submitted = await api.createJob(upload.id, quality);
  localStorage.setItem(ACTIVE_JOB_KEY, submitted.id);
  const job = await waitForServerJob(submitted.id);
  if (!job.project_id) throw new Error("后端未返回乐谱项目");
  serverProject = await api.getProject(job.project_id);
  applyApiProject(serverProject);
  void refreshProjects();
}
async function waitForServerJob(jobId: string) {
  try {
    const job = await api.waitForJobEvents(jobId, (current) =>
      status(
        `${JOB_STAGE_LABELS[current.stage]} · ${Math.round(current.progress * 100)}%`,
        current.progress * 100,
      ),
    );
    localStorage.removeItem(FAILED_JOB_KEY);
    $<HTMLButtonElement>("#retry-job").disabled = true;
    return job;
  } catch (error) {
    localStorage.setItem(FAILED_JOB_KEY, jobId);
    $<HTMLButtonElement>("#retry-job").disabled = false;
    throw error;
  } finally {
    localStorage.removeItem(ACTIVE_JOB_KEY);
  }
}
$("#retry-job").addEventListener("click", async () => {
  const failedJobId = localStorage.getItem(FAILED_JOB_KEY);
  if (!failedJobId) return;
  try {
    status("正在重新提交任务…", 2);
    const submitted = await api.retryJob(failedJobId);
    localStorage.setItem(ACTIVE_JOB_KEY, submitted.id);
    const job = await waitForServerJob(submitted.id);
    if (!job.project_id) throw new Error("重试任务没有乐谱项目");
    serverProject = await api.getProject(job.project_id);
    applyApiProject(serverProject);
    sync();
    render();
    void refreshProjects();
    status("重试任务已完成", 100);
  } catch (error) {
    status(`重试失败：${error instanceof Error ? error.message : "未知错误"}`, 0);
  }
});
async function resumeActiveJob() {
  const jobId = localStorage.getItem(ACTIVE_JOB_KEY);
  if (!jobId) return;
  try {
    status("正在恢复未完成任务…", 2);
    const job = await waitForServerJob(jobId);
    if (!job.project_id) throw new Error("恢复的任务没有乐谱项目");
    serverProject = await api.getProject(job.project_id);
    applyApiProject(serverProject);
    sync();
    render();
    status(
      `任务已恢复 · ${serverProject.source.file_name} · ${serverProject.notes.length} 个音符`,
      100,
    );
  } catch (error) {
    localStorage.removeItem(ACTIVE_JOB_KEY);
    status(`任务恢复失败：${error instanceof Error ? error.message : "未知错误"}`, 0);
  }
}
async function refreshProjects() {
  const select = $<HTMLSelectElement>("#recent-project");
  try {
    const projects = await api.listProjects();
    select.innerHTML =
      `<option value="">选择已保存项目…</option>` +
      projects
        .map(
          (project) =>
            `<option value="${project.project_id}">${project.file_name} · ${project.note_count} 音符 · r${project.revision}</option>`,
        )
        .join("");
    if (serverProject) select.value = serverProject.project_id;
  } catch {
    select.innerHTML = `<option value="">后端项目不可用</option>`;
  }
}
$<HTMLSelectElement>("#recent-project").addEventListener("change", async (event) => {
  const projectId = (event.currentTarget as HTMLSelectElement).value;
  $<HTMLButtonElement>("#delete-project").disabled = !projectId;
  if (!projectId) return;
  try {
    status("正在打开已保存项目…", 20);
    serverProject = await api.getProject(projectId);
    applyApiProject(serverProject);
    sync();
    render();
    status(`已恢复 ${serverProject.source.file_name} · 修订 ${serverProject.revision}`, 100);
  } catch (error) {
    status(`恢复失败：${error instanceof Error ? error.message : "未知错误"}`, 0);
  }
});
$("#refresh-projects").addEventListener("click", () => void refreshProjects());
$("#delete-project").addEventListener("click", async () => {
  const projectId = $<HTMLSelectElement>("#recent-project").value;
  if (!projectId || !confirm("确定删除这个项目、源音频和所有处理数据吗？此操作不可撤销。")) return;
  try {
    await api.deleteProject(projectId);
    if (serverProject?.project_id === projectId) {
      serverProject = null;
      scoreHistory = null;
      selectedNoteIndex = null;
      rawNotes = [];
      notes = [];
      $("#staff").innerHTML = "";
      $("#jianpu").innerHTML = "";
      $("#empty").classList.remove("hidden");
    }
    $<HTMLButtonElement>("#delete-project").disabled = true;
    await refreshProjects();
    status("项目及关联数据已删除", 0);
  } catch (error) {
    status(`删除失败：${error instanceof Error ? error.message : "未知错误"}`, 0);
  }
});
transcribe.addEventListener("click", async () => {
  if (!sourceBuffer) return;
  transcribe.disabled = true;
  try {
    const engine = $<HTMLSelectElement>("#engine").value;
    if (engine === "server-high") await runServer("high");
    else if (engine === "server-demo") await runServer("demo");
    else await runLocal();
    sync();
    render();
    status(
      `完成 · ${analysis.bpm} BPM · ${analysis.meter}/4 · ${keyName(analysis.keyPitchClass, analysis.mode)} · ${notes.length} 个音符`,
      100,
    );
  } catch (e) {
    console.error(e);
    status(`处理失败：${e instanceof Error ? e.message : "未知错误"}`, 0);
  } finally {
    transcribe.disabled = false;
  }
});
function sync() {
  bpm.value = String(analysis.bpm);
  meter.value = String(analysis.meter);
  key.value = String(analysis.keyPitchClass);
  mode.value = analysis.mode;
  $("#bpmConfidence").textContent = conf(analysis.confidence.bpm);
  $("#meterConfidence").textContent = conf(analysis.confidence.meter);
  $("#keyConfidence").textContent = conf(analysis.confidence.key);
}
async function update() {
  analysis = {
    ...analysis,
    bpm: Number(bpm.value),
    meter: Number(meter.value) as 3 | 4,
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
        denominator: 4,
        tonic: analysis.keyPitchClass,
        mode: analysis.mode,
        grid: 0.25,
      });
      applyApiProject(serverProject);
      render();
      status(`已保存 · 修订 ${serverProject.revision}`, 100);
    } catch (error) {
      status(
        `保存失败：${error instanceof Error ? error.message : "未知错误"}`,
      );
    }
  }
}
[bpm, meter, key, mode].forEach((el) => el.addEventListener("change", update));
$("#example").addEventListener("click", () => {
  serverProject = null;
  rawNotes = demoNotes();
  analysis = {
    bpm: 120,
    meter: 4,
    keyPitchClass: 0,
    mode: "major",
    confidence: { bpm: 0.92, meter: 0.81, key: 0.95 },
  };
  sync();
  render();
  status("已载入完整示例 · 所有参数均可修改", 100);
});
function render() {
  notes = cleanAndQuantize(
    rawNotes,
    analysis.bpm,
    keyRootMidi(analysis.keyPitchClass),
    analysis.mode,
  );
  $("#empty").classList.add("hidden");
  const abcKey =
    KEYS[analysis.keyPitchClass].replace("♯", "#") +
    (analysis.mode === "minor" ? "m" : "");
  ABCJS.renderAbc("staff", toAbc(notes, analysis.bpm, analysis.meter, abcKey), {
    responsive: "resize",
    add_classes: true,
    staffwidth: 860,
    wrap: {
      minSpacing: 1.7,
      maxSpacing: 2.7,
      preferredMeasuresPerLine: analysis.meter === 3 ? 6 : 4,
    },
  });
  $("#jianpu").innerHTML =
    `<div class="jianpu-meta">1 = ${KEYS[analysis.keyPitchClass]}　${analysis.meter}/4　♩ = ${analysis.bpm}<small>点击音符后按 ↑ / ↓ 升降半音</small></div>` +
    notes
      .map(
        (n, i) =>
          `<span class="jp-note${selectedNoteIndex === i ? " selected" : ""}" data-note="${i}" tabindex="0"><b>${n.accidental === 1 ? "♯" : n.accidental === -1 ? "♭" : ""}${n.degree}</b><em>${n.octave > 0 ? "·".repeat(n.octave) : ""}</em><i>${n.octave < 0 ? "·".repeat(-n.octave) : ""}</i><small>${n.durationBeats < 1 ? "━".repeat(Math.round(Math.log2(1 / n.durationBeats))) : n.durationBeats >= 2 ? "—" : ""}</small></span>`,
      )
      .join("");
  $("#piano").innerHTML = renderPianoRoll(notes, selectedNoteIndex);
  [play, $<HTMLButtonElement>("#midi"), $<HTMLButtonElement>("#xml")].forEach(
    (b) => (b.disabled = !notes.length),
  );
  const selected = selectedNoteIndex !== null && Boolean(notes[selectedNoteIndex]);
  ["#shorter", "#longer", "#split", "#merge", "#delete-note"].forEach(
    (selector) => ($<HTMLButtonElement>(selector).disabled = !selected || !scoreHistory),
  );
  $<HTMLButtonElement>("#undo").disabled = !scoreHistory?.canUndo;
  $<HTMLButtonElement>("#redo").disabled = !scoreHistory?.canRedo;
}
$<HTMLDivElement>("#jianpu").addEventListener("click", (event) => {
  const target = (event.target as HTMLElement).closest<HTMLElement>("[data-note]");
  if (!target) return;
  selectedNoteIndex = Number(target.dataset.note);
  render();
  document.querySelector<HTMLElement>(`[data-note="${selectedNoteIndex}"]`)?.focus();
});
$<HTMLDivElement>("#piano").addEventListener("click", (event) => {
  const target = (event.target as Element).closest<SVGElement>("[data-note]");
  if (!target) return;
  selectedNoteIndex = Number(target.dataset.note);
  render();
});
async function transposeSelected(semitones: number) {
  if (selectedNoteIndex === null || !notes[selectedNoteIndex]) return;
  const scoreNote = notes[selectedNoteIndex];
  const rawNote = rawNotes[scoreNote.id];
  if (!rawNote) return;
  if (!scoreHistory || !serverProject?.notes[selectedNoteIndex]) {
    rawNote.pitchMidi = Math.max(0, Math.min(127, rawNote.pitchMidi + semitones));
    render();
    return;
  }
  const current = serverProject.notes[selectedNoteIndex];
  const updated = scoreHistory.execute({
    type: "move",
    noteId: current.id,
    start: current.quantized_start,
    pitch: current.pitch_midi + semitones,
  });
  await saveEditedNotes(updated, "音高校正");
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
  if (!serverProject) return;
  useEditedNotes(updated);
  try {
    status(`正在保存${label}…`);
    serverProject = await api.updateProject(
      serverProject.project_id,
      serverProject.revision,
      updated,
    );
    status(`${label}已保存 · 修订 ${serverProject.revision}`, 100);
  } catch (error) {
    status(`保存失败：${error instanceof Error ? error.message : "未知错误"}`);
  }
}
document.addEventListener("keydown", (event) => {
  if (selectedNoteIndex === null || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
  event.preventDefault();
  void transposeSelected(event.key === "ArrowUp" ? 1 : -1);
});
function selectedEditableNote() {
  return selectedNoteIndex === null ? undefined : serverProject?.notes[selectedNoteIndex];
}
$("#delete-note").addEventListener("click", () => {
  const note = selectedEditableNote();
  if (note && scoreHistory)
    void saveEditedNotes(scoreHistory.execute({ type: "delete", noteId: note.id }), "删除");
});
$("#shorter").addEventListener("click", () => resizeSelected(-0.25));
$("#longer").addEventListener("click", () => resizeSelected(0.25));
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
  const right = selectedNoteIndex === null ? undefined : serverProject?.notes[selectedNoteIndex + 1];
  if (note && right && scoreHistory)
    void saveEditedNotes(
      scoreHistory.execute({ type: "merge", leftId: note.id, rightId: right.id }),
      "合并",
    );
});
$("#undo").addEventListener("click", () => {
  if (scoreHistory) void saveEditedNotes(scoreHistory.undo(), "撤销");
});
$("#redo").addEventListener("click", () => {
  if (scoreHistory) void saveEditedNotes(scoreHistory.redo(), "重做");
});
document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach((btn) =>
  btn.addEventListener("click", () => {
    document
      .querySelectorAll("[data-view]")
      .forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $("#staff").classList.toggle("hidden", btn.dataset.view !== "staff");
    $("#jianpu").classList.toggle("hidden", btn.dataset.view !== "jianpu");
    $("#piano").classList.toggle("hidden", btn.dataset.view !== "piano");
  }),
);
function stop() {
  timers.forEach(clearTimeout);
  timers = [];
  playing = false;
  play.textContent = "▶ 演奏";
  document
    .querySelectorAll(".playing")
    .forEach((e) => e.classList.remove("playing"));
}
play.addEventListener("click", async () => {
  if (playing) return stop();
  playing = true;
  play.textContent = "■ 停止";
  const ctx = new AudioContext();
  await ctx.resume();
  const beatMs = 60000 / analysis.bpm;
  notes.forEach((n, i) =>
    timers.push(
      window.setTimeout(() => {
        document
          .querySelectorAll(".playing")
          .forEach((e) => e.classList.remove("playing"));
        document.querySelector(`[data-note="${i}"]`)?.classList.add("playing");
        const osc = ctx.createOscillator(),
          gain = ctx.createGain();
        osc.type = "triangle";
        osc.frequency.value = 440 * 2 ** ((n.pitchMidi - 69) / 12);
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.16, ctx.currentTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(
          0.001,
          ctx.currentTime + Math.max(0.08, (n.durationBeats * beatMs) / 1000),
        );
        osc.connect(gain).connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + (n.durationBeats * beatMs) / 1000 + 0.05);
      }, n.startBeat * beatMs),
    ),
  );
  timers.push(
    window.setTimeout(
      stop,
      Math.max(...notes.map((n) => n.startBeat + n.durationBeats)) * beatMs +
        100,
    ),
  );
});
function downloadServerExport(format: "midi" | "musicxml") {
  if (!serverProject) return false;
  const link = document.createElement("a");
  link.href = api.exportUrl(serverProject.project_id, format);
  link.download = "";
  link.click();
  return true;
}
$("#midi").addEventListener("click", () => {
  if (!downloadServerExport("midi")) exportMidi(notes, analysis);
});
$("#xml").addEventListener("click", () => {
  if (!downloadServerExport("musicxml")) exportMusicXml(notes, analysis);
});
void refreshProjects();
void resumeActiveJob();
$<HTMLButtonElement>("#retry-job").disabled = !localStorage.getItem(FAILED_JOB_KEY);
