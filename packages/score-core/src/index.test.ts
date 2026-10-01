import { describe, expect, it } from "vitest";
import { ScoreHistory, applyCommand, type EditableNote } from "./index";

const note = (id: string, start = 0, pitch = 60): EditableNote => ({
  id,
  source_start_ms: start * 500,
  source_end_ms: start * 500 + 500,
  source_note_ids: [`source-${id}`],
  pitch_midi: pitch,
  confidence: 0.9,
  quantized_start: start,
  quantized_duration: 1,
  origin: "model",
});

describe("score commands", () => {
  it("adds, deletes, moves, and resizes notes without mutating input", () => {
    const original = [note("a")];
    const added = applyCommand(original, { type: "add", note: note("b", 2) });
    const moved = applyCommand(added, { type: "move", noteId: "b", start: 1, pitch: 64 });
    const resized = applyCommand(moved, { type: "resize", noteId: "b", duration: 0.5 });
    const deleted = applyCommand(resized, { type: "delete", noteId: "a" });
    expect(original[0].origin).toBe("model");
    expect(deleted).toMatchObject([
      { id: "b", quantized_start: 1, pitch_midi: 64, quantized_duration: 0.5 },
    ]);
  });

  it("splits a note while preserving source timing", () => {
    const result = applyCommand([note("a")], {
      type: "split",
      noteId: "a",
      at: 0.5,
      rightId: "b",
    });
    expect(result).toHaveLength(2);
    expect(result[0]).toMatchObject({ source_end_ms: 250, quantized_duration: 0.5 });
    expect(result[1]).toMatchObject({ source_start_ms: 250, quantized_start: 0.5 });
  });

  it("merges adjacent notes with the same pitch", () => {
    const result = applyCommand([note("a"), note("b", 1)], {
      type: "merge",
      leftId: "a",
      rightId: "b",
    });
    expect(result).toMatchObject([
      {
        id: "a",
        quantized_duration: 2,
        source_end_ms: 1000,
        source_note_ids: ["source-a", "source-b"],
      },
    ]);
  });
});

describe("history", () => {
  it("supports undo, redo, and clears redo after a new command", () => {
    const history = new ScoreHistory([note("a")]);
    history.execute({ type: "move", noteId: "a", start: 1, pitch: 62 });
    expect(history.canUndo).toBe(true);
    expect(history.undo()[0].pitch_midi).toBe(60);
    expect(history.redo()[0].pitch_midi).toBe(62);
    history.undo();
    history.execute({ type: "resize", noteId: "a", duration: 2 });
    expect(history.canRedo).toBe(false);
  });
});
