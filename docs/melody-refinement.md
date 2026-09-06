# Melody Refinement and Vocal Preview

High-quality transcription uses the existing Demucs neural separator and Basic Pitch neural
pitch detector. Basic Pitch is polyphonic; its output is not automatically a lead-vocal score.
The new refinement pass performs constrained Viterbi decoding over active note candidates,
using model confidence, a configurable vocal range, and pitch-continuity penalties. It is a
musical prior, not a generative model that knows the composer's intent. No external AI API,
credentials, or new model downloads are required by this pass.

## Controls

- Balanced and conservative modes select a monophonic line. The MIDI range defaults to 48-84.
- Short same-pitch fragments can be joined across gaps up to 80 ms (balanced) or 40 ms
  (conservative), only when at least one fragment is shorter than 180 ms.
- Full repeated notes, longer rests, and pitch changes are not forcibly joined.
- Raw mode restores the saved detector notes. On older projects, the first refinement saves
  the current notes as its baseline; re-transcribe to recover detections previously discarded.
- Reapplying refinement replaces note edits and creates a server revision. The UI asks before
  replacing edits in the current editing history. Export after checking the resulting score.

The same controls work in local browser mode without uploading audio. High-quality server
transcription applies balanced refinement by default. Retained `raw_notes` are stored with
the project JSON; no database migration is needed.

## Limits

Continuity alone cannot always distinguish a quieter lead singer from louder backing vocals.
Demucs vocals may contain harmony, reverberation and instrument leakage. Restrict the range
and compare the raw score and separated audio when results are uncertain. Synthetic tests
validate behavior, not transcription accuracy on a labeled singing dataset. A stronger next
step is a dedicated lead-vocal separator and evaluation on annotated recordings; do not
silently replace unusual phrasing with a supposedly more conventional composition.

## Cancellation and Preview

Cancel is available during upload, server work and local inference. Server subprocesses are
checked every 200 ms and terminated as a process group; neural inference runs in an owned
subprocess so it can also stop. This adds per-job model startup overhead. Atomic database
updates prevent cancelled tasks from later reporting success or persisting a project.
Browser inference uses a terminable Worker. Offline audio rendering may finish its current
operation before the cancellation check, but its result will not start inference afterward.

The source/vocals selector preserves the playback position and renders the separated waveform.
Local separation uses a center-vocal filter, not Demucs. Demo projects have no separated stem.
Existing high-quality projects with the old erroneous project-ID stem path are resolved using
their worker job ID. Missing stems show an unavailable state rather than playing the original
audio as if it were separated vocals.

## Verification

Run `npm test`, `npm run build`, and `.venv/bin/pytest -q`.
`scripts/check-transcription-ui.mjs` runs Chromium checks against `SCORE_URL` (default
`http://127.0.0.1:4180`). It uses a mock API on loopback port 4176 and synthetic audio, and
does not alter user projects. Set `PLAYWRIGHT_MODULE`, `CHROMIUM_PATH`, and `SCREENSHOT_DIR`
when using an externally provisioned Playwright installation.
