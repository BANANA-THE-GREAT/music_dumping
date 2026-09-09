import assert from "node:assert/strict";
import http from "node:http";
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)(
  process.env.PLAYWRIGHT_MODULE || "playwright",
);
const wav = Buffer.alloc(44 + 44100 * 2 * 2);
wav.write("RIFF");
wav.writeUInt32LE(wav.length - 8, 4);
wav.write("WAVE", 8);
wav.write("fmt ", 12);
wav.writeUInt32LE(16, 16);
wav.writeUInt16LE(1, 20);
wav.writeUInt16LE(1, 22);
wav.writeUInt32LE(44100, 24);
wav.writeUInt32LE(88200, 28);
wav.writeUInt16LE(2, 32);
wav.writeUInt16LE(16, 34);
wav.write("data", 36);
wav.writeUInt32LE(wav.length - 44, 40);
for (let i = 0; i < 88200; i++)
  wav.writeInt16LE(
    Math.round(Math.sin((i * 2 * Math.PI * 440) / 44100) * 10000),
    44 + i * 2,
  );
const raw = [60, 62, 64, 79].map((pitch, i) => ({
  id: `n${i}`,
  pitch_midi: pitch,
  source_start_ms: i < 3 ? i * 500 : 0,
  source_end_ms: i < 3 ? i * 500 + 450 : 1400,
  quantized_start: i < 3 ? i : 0,
  quantized_duration: i < 3 ? 1 : 3,
  confidence: i < 3 ? 0.9 : 0.3,
  origin: "model",
}));
const project = {
  schema_version: "1.0",
  project_id: "preview-test",
  revision: 1,
  source: {
    file_name: "preview-test.wav",
    duration_ms: 2000,
    audio_object_key: "test.wav",
    vocal_object_key: "vocals.wav",
  },
  analysis: {
    tempo_map: [{ time_ms: 0, bpm: 120 }],
    meter_map: [{ beat: 0, numerator: 4, denominator: 4 }],
    key_map: [{ beat: 0, tonic: 0, mode: "major" }],
    confidence: { tempo: 0.9, meter: 0.8, key: 0.9 },
  },
  notes: raw.slice(0, 3),
  raw_notes: raw,
  pipeline: [],
};
let job,
  events,
  cancels = 0;
const server = http.createServer((req, res) => {
  const path = new URL(req.url, "http://local").pathname;
  const json = (value, code = 200) => {
    req.resume();
    res.writeHead(code, { "content-type": "application/json" });
    res.end(JSON.stringify(value));
  };
  if (path === "/api/v1/project-catalog")
    return json([
      {
        project_id: project.project_id,
        project_group_id: "preview-group",
        upload_id: "preview-upload",
        project_name: "试听验收项目",
        score_name: "试听验收谱面",
        engine: "Basic Pitch",
        file_name: "preview-test.wav",
        duration_ms: 2000,
        note_count: project.notes.length,
        revision: project.revision,
        updated_at: new Date().toISOString(),
      },
    ]);
  if (path === "/api/v1/projects/preview-test") return json(project);
  if (path === "/api/v1/projects/preview-test/audio") {
    res.writeHead(200, { "content-type": "audio/wav" });
    res.end(wav);
    return;
  }
  if (path === "/api/v1/projects/preview-test/melody") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      const input = JSON.parse(body);
      assert.equal(input.expected_revision, project.revision);
      project.revision++;
      project.notes = input.mode === "raw" ? raw : raw.slice(0, 3);
      json(project);
    });
    return;
  }
  if (path === "/api/v1/uploads") return json({ id: "test-upload" }, 201);
  if (path === "/api/v1/jobs") {
    job = {
      id: "test-job",
      upload_id: "test-upload",
      status: "running",
      stage: "separating",
      progress: 0.3,
      project_id: null,
      error_message: null,
    };
    return json(job, 202);
  }
  if (path === "/api/v1/jobs/test-job/events") {
    events = res;
    res.writeHead(200, { "content-type": "text/event-stream" });
    res.write(`event: progress\ndata: ${JSON.stringify(job)}\n\n`);
    return;
  }
  if (path === "/api/v1/jobs/test-job/cancel") {
    cancels++;
    job.status = "cancelled";
    job.stage = "cancelled";
    json(job);
    events?.end(`event: progress\ndata: ${JSON.stringify(job)}\n\n`);
    return;
  }
  if (path === "/api/v1/jobs/test-job") return json(job);
  const upstream = http.request(
    new URL(req.url, process.env.SCORE_URL || "http://127.0.0.1:4180"),
    { method: req.method },
    (response) => {
      res.writeHead(response.statusCode, response.headers);
      response.pipe(res);
    },
  );
  upstream.on("error", () => {
    res.writeHead(502);
    res.end();
  });
  req.pipe(upstream);
});
await new Promise((resolve) => server.listen(4176, "127.0.0.1", resolve));
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH,
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1300, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
await page.addInitScript(() => {
  const Native = window.Worker;
  window.workerStops = 0;
  window.Worker = class extends Native {
    terminate() {
      window.workerStops++;
      super.terminate();
    }
  };
});
try {
  await page.goto("http://127.0.0.1:4176", { waitUntil: "domcontentloaded" });
  await page.click("#project-picker");
  await page.locator(".project-card").first().locator("summary").click();
  await page.locator('#project-list .score-option[data-score-id="preview-test"]').click();
  await page.waitForFunction(
    () => document.querySelectorAll("#piano rect").length === 3,
  );
  await page.locator('[name="audio-mode"][value="vocals"]').check();
  await page.waitForFunction(() =>
    document.querySelector("#audio").src.includes("variant=vocals"),
  );
  assert.ok(
    await page.evaluate(() =>
      document
        .querySelector("#vocal-waveform")
        .getContext("2d")
        .getImageData(0, 0, 900, 100)
        .data.some((x, i) => i % 4 === 3 && x > 0),
    ),
  );
  await page.locator('[name="audio-mode"][value="source"]').check();
  await page.selectOption("#melody-mode", "raw");
  await page.click("#refine-melody");
  await page.waitForFunction(
    () => document.querySelectorAll("#piano rect").length === 4,
  );
  await page.selectOption("#melody-mode", "balanced");
  await page.click("#refine-melody");
  await page.waitForFunction(
    () => document.querySelectorAll("#piano rect").length === 3,
  );
  await page.click("#transcribe");
  await page.waitForFunction(
    () =>
      document.querySelector('[data-task="separate"]').dataset.state ===
      "running",
  );
  await page.click("#cancel-job");
  await page.waitForFunction(() =>
    document.querySelector("#cancel-job").classList.contains("hidden"),
  );
  assert.equal(cancels, 1);
  assert.match(await page.locator("#status").innerText(), /取消/);
  assert.equal(
    await page.evaluate(() => localStorage.getItem("vocal-score.active-job")),
    null,
  );
  await page.selectOption("#engine", "local");
  await page.setInputFiles("#file", {
    name: "local-preview.wav",
    mimeType: "audio/wav",
    buffer: wav,
  });
  await page.waitForFunction(
    () => !document.querySelector("#transcribe").disabled,
  );
  await page.click("#transcribe");
  await page.waitForFunction(
    () =>
      document.querySelector('[data-task="transcribe"]').dataset.state ===
      "running",
  );
  await page.click("#cancel-job");
  await page.waitForFunction(() =>
    document.querySelector("#cancel-job").classList.contains("hidden"),
  );
  assert.ok(await page.evaluate(() => window.workerStops > 0));
  assert.equal(
    await page.locator('[name="audio-mode"][value="vocals"]').isEnabled(),
    true,
  );
  await page.locator('[name="audio-mode"][value="vocals"]').check();
  await page.waitForFunction(() =>
    document.querySelector("#audio").src.startsWith("blob:"),
  );
  await page.click("#transcribe");
  await page.waitForFunction(
    () =>
      ["completed", "failed"].includes(
        document.querySelector('[data-task="transcribe"]').dataset.state,
      ),
    null,
    { timeout: 120000 },
  );
  assert.equal(
    await page.locator('[data-task="transcribe"]').getAttribute("data-state"),
    "completed",
    await page.locator("#status").innerText(),
  );
  console.log("PASS: complete local Basic Pitch inference in a Web Worker");
  await page.click("#example");
  await page.screenshot({
    path: `${process.env.SCREENSHOT_DIR || "/tmp"}/transcription-desktop.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.screenshot({
    path: `${process.env.SCREENSHOT_DIR || "/tmp"}/transcription-mobile.png`,
    fullPage: true,
  });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  assert.deepEqual(errors, []);
  console.log(
    "PASS: server/local cancellation, model worker termination, source/vocal A-B, nonblank vocal waveform, raw restore/refine, desktop/mobile",
  );
} finally {
  events?.destroy();
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
