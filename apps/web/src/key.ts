const NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];

export const keyName = (pitchClass: number, mode: "major" | "minor") =>
  `${NAMES[pitchClass]} ${mode === "major" ? "大调" : "小调"}`;

export const keyRootMidi = (pitchClass: number) => 60 + pitchClass;
