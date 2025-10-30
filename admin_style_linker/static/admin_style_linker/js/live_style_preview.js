document.addEventListener('DOMContentLoaded', () => {
    // Objects to store initialized editors
    const monacoInstances = {}; // {fieldName: monacoEditorInstance}
    const tinymceInstances = {}; // {fieldName_lang: tinymceEditorInstance}

    // Function to get the base field name and language (for modeltranslation)
    function getFieldInfo(elementId) {
        // ID can be 'id_message_uk' or 'id_styles'
        const parts = elementId.replace('id_', '').split('_');
        const baseName = parts[0];
        // If there is a language suffix and it consists of 2 letters
        const lang = parts.length > 1 && parts[parts.length - 1].length === 2
            ? parts[parts.length - 1]
            : null;

        if (lang) {
            return { baseName: parts.slice(0, -1).join('_'), lang: lang };
        }
        return { baseName: baseName, lang: null };
    }

    // Initialize Monaco Editor
    document.addEventListener('monacoEditorReady', (event) => {
        const { editor, container: element } = event.detail;
        const sourceFor = element.dataset.styleSourceFor;
        if (sourceFor) {
            // const { baseName } = getFieldInfo(element.id);
            const baseName = element.id.replace('id_', '')
            monacoInstances[baseName] = editor;
            console.log(`Monaco Editor registered for source: ${baseName}`);
            linkEditors();
        }
    });

    // Initialize TinyMCE Editor
    document.addEventListener('tinyMceAllEditorsInit', (event) => {
        const editors = event.detail;
        editors.forEach(editor => {
            const textarea = editor.getElement();
            const targetOf = textarea.dataset.styleTargetOf;
            if (targetOf) {
                const { baseName, lang } = getFieldInfo(textarea.id);
                const key = lang ? `${baseName}_${lang}` : baseName;
                tinymceInstances[key] = editor;
                console.log(`TinyMCE Editor registered for target: ${key}`);
            }
        });
        linkEditors();
    });

    function linkEditors() {
        // Loop through all target (TinyMCE) editors
        for (const tinymceKey in tinymceInstances) {
            const tinymceEditor = tinymceInstances[tinymceKey];
            const textarea = tinymceEditor.getElement();
            const styleSourceName = textarea.dataset.styleTargetOf; // e.g., 'styles'
            const { baseName: htmlBaseName, lang } = getFieldInfo(textarea.id); // e.g., 'message', 'en'

            if (!styleSourceName) continue;

            // Logic for modeltranslation
            // 1. Look for styles for a specific language (e.g., 'styles_en')
            let sourceMonacoEditor = monacoInstances[`${styleSourceName}_${lang}`];

            // 2. If not found, look for the base (single-language) style (e.g., 'styles')
            if (!sourceMonacoEditor) {
                sourceMonacoEditor = monacoInstances[styleSourceName];
            }

            if (sourceMonacoEditor) {
                console.log(`Linking ${tinymceKey} with style source ${styleSourceName}`);

                // Attach an event handler to the Monaco content change
                // Use ._linked to avoid attaching multiple listeners
                if (!sourceMonacoEditor._linked) {
                    sourceMonacoEditor._linked = new Set();
                    sourceMonacoEditor.onDidChangeModelContent(() => {
                        updateLinkedTinyMCE(sourceMonacoEditor);
                    });
                }
                sourceMonacoEditor._linked.add(tinymceEditor);

                // Apply styles immediately on load
                updateTinyMCEStyles(tinymceEditor, sourceMonacoEditor.getValue());
            }
        }
    }

    function updateLinkedTinyMCE(monacoEditor) {
        if (monacoEditor._linked) {
            const monacoCSS = monacoEditor.getValue();
            monacoEditor._linked.forEach(tinymceEditor => {
                updateTinyMCEStyles(tinymceEditor, monacoCSS);
            });
        }
    }

    function updateTinyMCEStyles(tinymceEditor, cssContent) {
        if (!tinymceEditor || !tinymceEditor.contentDocument) {
            // The editor may not be fully ready yet
            return;
        }
        const head = tinymceEditor.contentDocument.head;
        let styleTag = head.querySelector('style#live-preview-styles');
        if (!styleTag) {
            styleTag = document.createElement('style');
            styleTag.id = 'live-preview-styles';
            head.appendChild(styleTag);
        }
        styleTag.innerHTML = cssContent;
    }
  });
