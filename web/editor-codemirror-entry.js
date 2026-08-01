import { basicSetup } from "codemirror";
import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";
import { indentUnit } from "@codemirror/language";
import { EditorState, StateEffect, StateField } from "@codemirror/state";
import { Decoration, EditorView, keymap } from "@codemirror/view";

const setErrorLine = StateEffect.define();
const errorLineField = StateField.define({
  create() { return Decoration.none; },
  update(value, transaction) {
    value = value.map(transaction.changes);
    for (const effect of transaction.effects) {
      if (!effect.is(setErrorLine)) continue;
      if (!effect.value) return Decoration.none;
      const line = Math.max(1, Math.min(effect.value, transaction.state.doc.lines));
      return Decoration.set([
        Decoration.line({ class: "cm-build-error-line" }).range(transaction.state.doc.line(line).from),
      ]);
    }
    return value;
  },
  provide: field => EditorView.decorations.from(field),
});

window.createEbmCodeEditor = function createEbmCodeEditor(parent, options = {}) {
  let suppressChanges = false;
  const runKeymap = keymap.of([{
    key: "Mod-Enter",
    run() {
      options.onRun?.();
      return true;
    },
  }]);
  const view = new EditorView({
    parent,
    state: EditorState.create({
      doc: options.doc || "",
      extensions: [
        basicSetup,
        python(),
        oneDark,
        errorLineField,
        runKeymap,
        EditorView.lineWrapping,
        EditorState.tabSize.of(4),
        indentUnit.of("    "),
        EditorView.updateListener.of(update => {
          if (update.docChanged && !suppressChanges) options.onChange?.(update.state.doc.toString());
          if (update.selectionSet || update.docChanged) {
            const position = update.state.selection.main.head;
            const line = update.state.doc.lineAt(position);
            options.onCursor?.(line.number, position - line.from + 1);
          }
        }),
        EditorView.theme({
          "&": { height: "100%", fontSize: "13px" },
          ".cm-scroller": { overflow: "auto", fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace", lineHeight: "1.55" },
          ".cm-content": { padding: "12px 0" },
          ".cm-gutters": { backgroundColor: "#0b1220", color: "#52657b", border: "none" },
          ".cm-activeLineGutter": { backgroundColor: "#172033" },
          ".cm-build-error-line": { backgroundColor: "rgba(153, 27, 27, .42)" },
        }),
      ],
    }),
  });

  return {
    getValue() { return view.state.doc.toString(); },
    setValue(value) {
      suppressChanges = true;
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } });
      suppressChanges = false;
      options.onCursor?.(1, 1);
    },
    focus() { view.focus(); },
    setErrorLine(line) { view.dispatch({ effects: setErrorLine.of(line || null) }); },
    destroy() { view.destroy(); },
  };
};
