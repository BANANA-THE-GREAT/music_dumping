export interface EditableNote {
  id: string;
  source_start_ms: number;
  source_end_ms: number;
  pitch_midi: number;
  confidence: number;
  quantized_start: number;
  quantized_duration: number;
  origin: "model" | "user";
}

export type ScoreCommand =
  | { type: "add"; note: EditableNote }
  | { type: "delete"; noteId: string }
  | { type: "move"; noteId: string; start: number; pitch: number }
  | { type: "resize"; noteId: string; duration: number }
  | { type: "split"; noteId: string; at: number; rightId: string }
  | { type: "merge"; leftId: string; rightId: string };

const clone = (notes: EditableNote[]) => notes.map((note) => ({ ...note }));
const positive = (value: number) => Math.max(0.125, value);

export function applyCommand(notes: EditableNote[], command: ScoreCommand): EditableNote[] {
  const next = clone(notes);
  switch (command.type) {
    case "add":
      return [...next, { ...command.note, origin: "user" as const }].sort(
        (left, right) => left.quantized_start - right.quantized_start,
      );
    case "delete":
      return next.filter((note) => note.id !== command.noteId);
    case "move":
      return next
        .map((note) =>
          note.id === command.noteId
            ? {
                ...note,
                quantized_start: Math.max(0, command.start),
                pitch_midi: Math.max(0, Math.min(127, command.pitch)),
                origin: "user" as const,
              }
            : note,
        )
        .sort((left, right) => left.quantized_start - right.quantized_start);
    case "resize":
      return next.map((note) =>
        note.id === command.noteId
          ? { ...note, quantized_duration: positive(command.duration), origin: "user" }
          : note,
      );
    case "split":
      return next.flatMap((note) => {
        if (note.id !== command.noteId) return note;
        const offset = command.at - note.quantized_start;
        if (offset < 0.125 || note.quantized_duration - offset < 0.125) return note;
        const sourceSplit = Math.round(
          note.source_start_ms +
            ((note.source_end_ms - note.source_start_ms) * offset) /
              note.quantized_duration,
        );
        return [
          {
            ...note,
            source_end_ms: sourceSplit,
            quantized_duration: offset,
            origin: "user" as const,
          },
          {
            ...note,
            id: command.rightId,
            source_start_ms: sourceSplit,
            quantized_start: command.at,
            quantized_duration: note.quantized_duration - offset,
            origin: "user" as const,
          },
        ];
      });
    case "merge": {
      const left = next.find((note) => note.id === command.leftId);
      const right = next.find((note) => note.id === command.rightId);
      if (!left || !right || left.pitch_midi !== right.pitch_midi) return next;
      const end = Math.max(
        left.quantized_start + left.quantized_duration,
        right.quantized_start + right.quantized_duration,
      );
      return next
        .filter((note) => note.id !== right.id)
        .map((note) =>
          note.id === left.id
            ? {
                ...note,
                source_end_ms: Math.max(left.source_end_ms, right.source_end_ms),
                quantized_duration: end - left.quantized_start,
                origin: "user" as const,
              }
            : note,
        );
    }
  }
}

export class ScoreHistory {
  private past: EditableNote[][] = [];
  private future: EditableNote[][] = [];

  constructor(private current: EditableNote[]) {
    this.current = clone(current);
  }

  execute(command: ScoreCommand): EditableNote[] {
    this.past.push(clone(this.current));
    this.current = applyCommand(this.current, command);
    this.future = [];
    return this.value;
  }

  undo(): EditableNote[] {
    const previous = this.past.pop();
    if (!previous) return this.value;
    this.future.push(clone(this.current));
    this.current = previous;
    return this.value;
  }

  redo(): EditableNote[] {
    const next = this.future.pop();
    if (!next) return this.value;
    this.past.push(clone(this.current));
    this.current = next;
    return this.value;
  }

  replace(notes: EditableNote[]): EditableNote[] {
    this.current = clone(notes);
    this.past = [];
    this.future = [];
    return this.value;
  }

  get canUndo(): boolean {
    return this.past.length > 0;
  }

  get canRedo(): boolean {
    return this.future.length > 0;
  }

  get value(): EditableNote[] {
    return clone(this.current);
  }
}
