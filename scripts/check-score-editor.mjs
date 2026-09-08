import assert from "node:assert/strict";
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)(
  process.env.PLAYWRIGHT_MODULE || "playwright",
);
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH,
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1300, height: 1000 } });
const errors = [];
await page.addInitScript(() => {
  const NativeContext = window.AudioContext;
  window.audioProbe = { contexts: 0, starts: [], stops: [], analyser: null };
  window.AudioContext = class extends NativeContext {
    constructor(options) {
      super(options);
      window.audioProbe.contexts++;
    }
    createOscillator() {
      const node = super.createOscillator();
      const start = node.start.bind(node),
        stop = node.stop.bind(node);
      node.start = (time) => {
        window.audioProbe.starts.push(time);
        start(time);
      };
      node.stop = (time) => {
        window.audioProbe.stops.push(time);
        stop(time);
      };
      return node;
    }
    createDynamicsCompressor() {
      const node = super.createDynamicsCompressor();
      const connect = node.connect.bind(node);
      const analyser = this.createAnalyser();
      window.audioProbe.analyser = analyser;
      node.connect = (destination) => {
        connect(analyser);
        return analyser.connect(destination);
      };
      return node;
    }
  };
});
page.on("pageerror", (error) => errors.push(error.message));
await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
try {
  await page.goto(process.env.SCORE_URL || "http://127.0.0.1:4180");
  await page.click("#example");
  await page.waitForSelector('#staff [data-note="0"]');
  await page.locator('#staff [data-note="0"]').first().click();
  assert.equal(await page.locator("#pitch-up").isEnabled(), true);
  await page.click("#pitch-up");
  await page.waitForFunction(
    () =>
      document.querySelector("#piano rect title")?.textContent === "MIDI 61",
  );
  await page.click("#undo");
  await page.waitForFunction(
    () =>
      document.querySelector("#piano rect title")?.textContent === "MIDI 60",
  );
  await page.click('[data-view="jianpu"]');
  assert.equal(await page.locator(".jp-measure").count(), 4);
  await page.locator('#jianpu [data-note="1"]').first().click();
  await page.keyboard.press("ArrowUp");
  await page.waitForFunction(
    () =>
      document.querySelector('#piano rect[data-note="1"] title')
        ?.textContent === "MIDI 61",
  );
  await page.click("#shorter");
  await page.click("#split");
  await page.waitForFunction(
    () => document.querySelectorAll("#piano rect").length === 15,
  );
  await page.click("#example");
  await page.waitForFunction(
    () => document.querySelectorAll("#piano rect").length === 14,
  );
  await page.click('[data-view="piano"]');
  const rect = await page.locator("#piano svg").boundingBox();
  await page.mouse.move(rect.x + 200, rect.y + 100);
  await page.keyboard.down("Control");
  await page.mouse.wheel(0, -400);
  await page.keyboard.up("Control");
  await page.waitForFunction(
    () => Number(document.querySelector("#zoom").value) > 1,
  );
  assert.ok(
    (await page.locator("#piano svg").boundingBox()).width > rect.width,
  );
  await page.locator("#zoom").fill("1");
  await page.locator("#zoom").dispatchEvent("input");
  const target = await page.locator('#piano rect[data-note="0"]').boundingBox();
  await page.mouse.move(
    target.x + target.width / 2,
    target.y + target.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    target.x + target.width / 2 + 35,
    target.y + target.height / 2 - 25,
  );
  await page.mouse.up();
  await page.waitForFunction(
    () => document.querySelector("#undo").disabled === false,
  );
  await page.click('[data-view="staff"]');
  await page.click("#example");
  await page.waitForFunction(
    () => document.querySelectorAll("#piano rect").length === 14,
  );
  await page.click("#play");
  await page.waitForFunction(
    () =>
      document.querySelector("#staff .playing") &&
      document.querySelector("#jianpu .playing") &&
      document.querySelector("#piano .playing"),
  );
  assert.equal(await page.evaluate(() => window.audioProbe.starts.length), 14);
  const rms = await page.evaluate(async () => {
    await new Promise((resolve) => setTimeout(resolve, 180));
    const samples = new Float32Array(2048);
    window.audioProbe.analyser.getFloatTimeDomainData(samples);
    return Math.sqrt(
      samples.reduce((sum, x) => sum + x * x, 0) / samples.length,
    );
  });
  assert.ok(rms > 0.01, `Expected audible sustained signal, RMS=${rms}`);
  await page.evaluate(() => {
    const until = performance.now() + 650;
    while (performance.now() < until) {}
  });
  await page.waitForFunction(
    () =>
      document.querySelector('#staff [data-note="1"].playing') ||
      document.querySelector('#staff [data-note="2"].playing'),
  );
  await page.click("#play");
  assert.equal(await page.locator(".playing").count(), 0);
  assert.equal(await page.evaluate(() => window.audioProbe.stops.length), 28);
  await page.click("#play");
  await page.waitForFunction(() => window.audioProbe.starts.length === 28);
  assert.equal(await page.evaluate(() => window.audioProbe.contexts), 1);
  await page.click("#play");
  console.log(
    "PASS: synchronized highlights, sustained audio output, pre-scheduling during main-thread blocking, stop and context reuse",
  );
  await page.locator("#bpm").fill("240");
  await page.locator("#bpm").dispatchEvent("change");
  await page.click("#play");
  await page.waitForFunction(() => window.audioProbe.starts.length === 42);
  await page.waitForFunction(() =>
    document.querySelector("#play").textContent.includes("演奏"),
  );
  assert.equal(await page.locator(".playing").count(), 0);
  await page.waitForTimeout(100);
  assert.equal(
    await page.evaluate(() => {
      const samples = new Float32Array(2048);
      window.audioProbe.analyser.getFloatTimeDomainData(samples);
      return samples.some((value) => Math.abs(value) > 0.0001);
    }),
    false,
  );
  console.log("PASS: natural completion and silent cleanup");
  await page.screenshot({
    path: `${process.env.SCREENSHOT_DIR || "/tmp"}/score-desktop.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.click('[data-view="jianpu"]');
  await page.screenshot({
    path: `${process.env.SCREENSHOT_DIR || "/tmp"}/score-mobile.png`,
    fullPage: true,
  });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  assert.deepEqual(errors, []);
  const project = {
    schema_version: "1.0",
    project_id: "editor-check",
    revision: 1,
    source: {
      file_name: "editor-check.wav",
      duration_ms: 2000,
      audio_object_key: "",
      vocal_object_key: null,
    },
    analysis: {
      tempo_map: [{ time_ms: 0, bpm: 120 }],
      meter_map: [{ beat: 0, numerator: 4, denominator: 4 }],
      key_map: [{ beat: 0, tonic: 0, mode: "major" }],
      confidence: { tempo: 0.9, meter: 0.9, key: 0.9 },
    },
    quantization: {
      enabled: true,
      grid: 0.25,
      strength: 1,
      offset_ms: 0,
      conflicts: [],
    },
    notes: [60, 64].map((pitch, index) => ({
      id: `saved-${index}`,
      source_note_ids: [`source-${index}`],
      pitch_midi: pitch,
      source_start_ms: index * 500,
      source_end_ms: index * 500 + 500,
      quantized_start: index,
      quantized_duration: 1,
      confidence: 0.9,
      origin: "model",
    })),
    transcription_evidence: {
      note_model: {
        name: "GAME medium",
        implementation: "browser-check",
        code_revision: "test",
        parameters: {},
      },
      f0_track: {
        object_key: "work/editor-check/evidence/f0.jsonl",
        format: "jsonl",
        frame_period_ms: 10,
        frame_count: 3,
        voiced_frame_count: 3,
        duration_ms: 30,
        provenance: {
          name: "torchcrepe full",
          implementation: "browser-check",
          code_revision: "test",
          parameters: {},
        },
      },
      boundary_suggestions: [
        {
          id: "boundary-1",
          source_note_id: "source-0",
          kind: "adjust_end",
          original_end_ms: 500,
          proposed_end_ms: 570,
          confidence: 0.9,
          reason: "f0_voicing_extension",
          review_status: "pending",
        },
      ],
    },
    pipeline: [],
  };
  const saved = [];
  await page.route("**/api/v1/projects", (route) =>
    route.fulfill({
      json: [
        {
          project_id: project.project_id,
          file_name: "editor-check.wav",
          note_count: 2,
          revision: project.revision,
        },
      ],
    }),
  );
  await page.route("**/api/v1/projects/editor-check/audio", (route) =>
    route.abort(),
  );
  await page.route("**/api/v1/projects/editor-check/evidence/f0", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        '{"time_seconds":0,"f0_hz":261.63,"periodicity":0.9}\n' +
        '{"time_seconds":0.01,"f0_hz":262,"periodicity":0.8}\n' +
        '{"time_seconds":0.02,"f0_hz":262.2,"periodicity":0.85}\n',
    }),
  );
  await page.route(
    "**/api/v1/projects/editor-check/boundary-suggestions/boundary-1",
    async (route) => {
      const body = route.request().postDataJSON();
      assert.equal(body.expected_revision, project.revision);
      const suggestion = project.transcription_evidence.boundary_suggestions[0];
      if (body.action === "accept") {
        project.notes[0].source_end_ms = suggestion.proposed_end_ms;
        suggestion.review_status = "accepted";
      } else if (body.action === "reset") {
        project.notes[0].source_end_ms = suggestion.original_end_ms;
        suggestion.review_status = "pending";
      } else suggestion.review_status = "rejected";
      project.revision++;
      await route.fulfill({ json: project });
    },
  );
  let requantizeRequest;
  await page.route(
    "**/api/v1/projects/editor-check/requantize",
    async (route) => {
      requantizeRequest = route.request().postDataJSON();
      assert.equal(requantizeRequest.expected_revision, project.revision);
      project.quantization = {
        enabled: requantizeRequest.enabled,
        grid: requantizeRequest.grid,
        strength: requantizeRequest.strength,
        offset_ms: requantizeRequest.offset_ms,
        conflicts: [{ beat: 1, note_ids: ["saved-0", "saved-1"] }],
      };
      project.revision++;
      await route.fulfill({ json: project });
    },
  );
  await page.route("**/api/v1/projects/editor-check", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON();
      assert.equal(body.expected_revision, project.revision);
      saved.push(body);
      project.notes = body.notes;
      project.revision++;
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
    await route.fulfill({ json: project });
  });
  await page.click("#refresh-projects");
  await page
    .locator('#recent-project option[value="editor-check"]')
    .waitFor({ state: "attached" });
  await page.selectOption("#recent-project", "editor-check");
  await page.waitForFunction(
    () => document.querySelectorAll("#piano rect").length === 2,
  );
  await page.selectOption("#quantize-grid", "0.3333333333333333");
  await page.fill("#quantize-strength", "50");
  await page.fill("#quantize-offset", "40");
  await page.click("#apply-quantization");
  await page.waitForFunction(() =>
    document.querySelector("#quantization-result").textContent.includes("1 处"),
  );
  assert.equal(requantizeRequest.grid, 1 / 3);
  assert.equal(requantizeRequest.strength, 0.5);
  assert.equal(requantizeRequest.offset_ms, 40);
  await page.locator(".boundary-locate").click();
  assert.equal(await page.locator("#piano").isVisible(), true);
  assert.equal(await page.locator("#piano .f0-track").count(), 1);
  assert.equal(await page.locator("#piano .boundary-guide.pending").count(), 1);
  await page.locator('[data-boundary-action="accept"]').click();
  await page.waitForFunction(
    () => document.querySelector(".boundary-state.accepted"),
  );
  assert.equal(project.notes[0].source_end_ms, 570);
  await page.locator('[data-boundary-action="reset"]').click();
  await page.waitForFunction(
    () => document.querySelector('[data-boundary-action="accept"]'),
  );
  assert.equal(project.notes[0].source_end_ms, 500);
  await page.click('[data-view="jianpu"]');
  await page.locator('#jianpu [data-note="0"]').first().click();
  await page.click("#pitch-up");
  await page.waitForFunction(() =>
    document.querySelector("#status").textContent.includes("修订 5"),
  );
  assert.equal(project.notes[0].pitch_midi, 61);
  await page.click("#undo");
  await page.waitForFunction(() =>
    document.querySelector("#status").textContent.includes("修订 6"),
  );
  assert.equal(project.notes[0].pitch_midi, 60);
  assert.equal(saved.length, 2);
  await page.click("#example");
  await page.waitForFunction(
    () => document.querySelectorAll("#piano rect").length === 14,
  );
  assert.deepEqual(errors, []);
  console.log(
    "PASS: quantization controls, F0 overlay, boundary review, revision sequencing and local reset (mock API only)",
  );
  console.log(
    "PASS: staff selection, cross-view pitch editing, undo, numbered bars, split, example reset, Ctrl-wheel zoom, drag, desktop/mobile layout",
  );
} finally {
  await browser.close();
}
