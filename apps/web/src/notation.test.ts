import { describe, expect, it } from "vitest";
import { cleanAndQuantize, demoNotes, mappedAbc } from "./music";
import { renderJianpu, scoreMeasures } from "./notation";

const note = cleanAndQuantize(demoNotes(), 120)[0];
describe("notation measures and identity", () => {
  it("splits sustained notes and rests across compound meter measures", () => {
    const measures = scoreMeasures(
      [{ ...note, startBeat: 4, durationBeats: 4 }],
      3,
    );
    expect(
      measures.map((m) => m.reduce((sum, s) => sum + s.duration, 0)),
    ).toEqual([3, 3, 2]);
    expect(measures[1][1]).toMatchObject({
      index: 0,
      duration: 2,
      continues: true,
    });
    expect(measures[2][0]).toMatchObject({
      index: 0,
      duration: 2,
      continues: false,
    });
  });
  it("renders numbered barlines and rests without selectable rest IDs", () => {
    const html = renderJianpu([{ ...note, startBeat: 4, durationBeats: 1 }], 4);
    expect(html.match(/class="jp-measure"/g)).toHaveLength(2);
    expect(html).toContain("<b>0</b>");
    expect(html.match(/data-note=/g)).toHaveLength(1);
  });
  it("maps both tied staff fragments to the original editable note", () => {
    const result = mappedAbc(
      [{ ...note, startBeat: 3.75, durationBeats: 0.5 }],
      120,
    );
    expect(result.mapping.map((m) => m.index)).toEqual([0, 0]);
    expect(result.abc.slice(result.mapping[0].offset)).toContain(
      "=C2/4- | =C2/4",
    );
  });
  it("preserves sixteenth and thirty-second note values", () => {
    expect(mappedAbc([{ ...note, durationBeats: 0.125 }], 120).abc).toContain(
      "=C1/4",
    );
  });
  it("handles empty scores", () => {
    expect(scoreMeasures([], 4)).toEqual([]);
  });
});
