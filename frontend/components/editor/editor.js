import {basicSetup} from "codemirror";
import {EditorState} from "@codemirror/state";
import {EditorView, keymap} from "@codemirror/view";
import {indentWithTab} from "@codemirror/commands";
import {python} from "@codemirror/lang-python";
import {cpp} from "@codemirror/lang-cpp";

export default function(component) {
  const {data, parentElement, setTriggerValue} = component;
  const root = parentElement.querySelector(".oj-editor");
  const storageKey = `oj-code:${data.user}:${data.problem}:${data.language}`;
  let initial = "";
  try {
    initial = sessionStorage.getItem(storageKey) || "";
    sessionStorage.setItem("oj-code-user", String(data.user));
  } catch (_) {}
  const language = /^(python|py)/i.test(data.language) ? python()
    : /^(cpp|c\+\+)/i.test(data.language) ? cpp() : [];
  const save = (code) => { try { sessionStorage.setItem(storageKey, code); } catch (_) {} };
  const editor = new EditorView({
    parent: root,
    state: EditorState.create({doc: initial, extensions: [
      basicSetup, language, EditorView.lineWrapping, keymap.of([indentWithTab]),
      EditorView.contentAttributes.of({"aria-label": "代码", "spellcheck": "false"}),
      EditorView.updateListener.of(update => {
        if (update.docChanged) save(update.state.doc.toString());
      }),
      EditorView.theme({
        "&": {backgroundColor: "#ffffff", color: "#17243b", fontSize: "16px"},
        ".cm-scroller": {overflow: "visible", fontFamily: "Consolas, monospace"},
        ".cm-content": {minHeight: "240px", padding: "12px 0", caretColor: "#2563eb"},
        ".cm-gutters": {backgroundColor: "#f2f5fc", color: "#66758b", border: "none"},
        ".cm-activeLine": {backgroundColor: "#eef4ff"},
        "&.cm-focused": {outline: "2px solid #818cf8", outlineOffset: "2px"}
      })
    ]})
  });
  const button = parentElement.querySelector("button");
  button.addEventListener("click", () => {
    if (editor.composing || button.disabled) return;
    const code = editor.state.doc.toString();
    save(code);
    if (!code.trim()) {
      parentElement.querySelector("[role=status]").textContent = "请输入代码。";
      return;
    }
    button.disabled = true;
    button.textContent = "正在提交…";
    setTriggerValue("submission", {code, language: data.language, event_id: crypto.randomUUID()});
  });
  return () => { save(editor.state.doc.toString()); editor.destroy(); };
}
