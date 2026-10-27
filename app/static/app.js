// Makes the page work: calls the API and puts the results on the page.
// Safety rule: text from documents and answers goes on the page ONLY with
// textContent, never innerHTML, so it is always shown as plain text.

const $ = (id) => document.getElementById(id);

const workspaceSelect = $("workspace-select");
const documentList = $("document-list");
const fileInput = $("file-input");
const questionBox = $("question");


// --- talking to the API ---

async function api(method, path, body) {
    const options = { method };
    if (body instanceof FormData) {
        options.body = body;  // a file upload; the browser sets the headers
    } else if (body !== undefined) {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify(body);
    }

    let response;
    try {
        response = await fetch(path, options);
    } catch {
        throw new Error("Can't reach the app. Is the server still running?");
    }

    if (response.status === 204) return null;  // deleted: no body to read
    const data = await response.json().catch(() => null);
    if (!response.ok) {
        // Our API always sends {"detail": "friendly message"}.
        const detail = data && typeof data.detail === "string" ? data.detail : "Something went wrong.";
        throw new Error(detail);
    }
    return data;
}


// --- "Processing...", disabled buttons, and errors ---

async function busy(message, work) {
    setDisabled(true);
    $("status").textContent = message;
    $("error").textContent = "";
    try {
        await work();
    } catch (error) {
        $("error").textContent = error.message;
    } finally {
        setDisabled(false);
        $("status").textContent = "";
    }
}

function setDisabled(disabled) {
    for (const element of document.querySelectorAll("button, input, select, textarea")) {
        element.disabled = disabled;
    }
    if (!disabled && !currentWorkspace()) {
        // No workspace yet: only "New workspace" makes sense.
        for (const element of [$("delete-workspace"), fileInput, questionBox,
                               ...document.querySelectorAll("#upload-form button, #ask-form button")]) {
            element.disabled = true;
        }
    }
}

function currentWorkspace() {
    return workspaceSelect.value;  // "" when there are no workspaces
}


// --- workspaces ---

async function loadWorkspaces(selectId) {
    const workspaces = await api("GET", "/api/workspaces");
    workspaceSelect.replaceChildren();

    if (workspaces.length === 0) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No workspaces yet: create one below";
        workspaceSelect.append(option);
    }
    for (const workspace of workspaces) {
        const option = document.createElement("option");
        option.value = workspace.id;
        option.textContent = workspace.name;
        workspaceSelect.append(option);
    }
    if (selectId !== undefined) workspaceSelect.value = String(selectId);

    hideAnswer();
    await loadDocuments();
}

$("new-workspace-form").addEventListener("submit", (event) => {
    event.preventDefault();  // stop the browser from reloading the page
    const name = $("new-workspace-name").value;
    busy("Creating workspace...", async () => {
        const workspace = await api("POST", "/api/workspaces", { name });
        $("new-workspace-name").value = "";
        await loadWorkspaces(workspace.id);
    });
});

workspaceSelect.addEventListener("change", () => {
    hideAnswer();
    busy("Loading...", loadDocuments);
});

$("delete-workspace").addEventListener("click", () => {
    const id = currentWorkspace();
    const name = workspaceSelect.selectedOptions[0].textContent;
    if (!id || !confirm(`Delete the workspace "${name}" and all its documents?`)) return;
    busy("Deleting workspace...", async () => {
        await api("DELETE", `/api/workspaces/${id}`);
        await loadWorkspaces();
    });
});


// --- documents ---

async function loadDocuments() {
    documentList.replaceChildren();
    const id = currentWorkspace();
    if (!id) return;

    const documents = await api("GET", `/api/workspaces/${id}/documents`);
    if (documents.length === 0) {
        const item = document.createElement("li");
        item.className = "muted";
        item.textContent = "No documents yet. Upload a PDF, Word, .txt or .md file.";
        documentList.append(item);
    }
    for (const doc of documents) {
        const item = document.createElement("li");
        item.className = "doc-item";

        const name = document.createElement("span");
        name.textContent = doc.filename;

        const button = document.createElement("button");
        button.type = "button";
        button.className = "danger";
        button.textContent = "Delete";
        button.addEventListener("click", () => {
            if (!confirm(`Delete ${doc.filename}?`)) return;
            busy("Deleting...", async () => {
                await api("DELETE", `/api/documents/${doc.id}`);
                hideAnswer();
                await loadDocuments();
            });
        });

        item.append(name, button);
        documentList.append(item);
    }
}

$("upload-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const file = fileInput.files[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    busy(`Processing ${file.name}... (big files can take a minute)`, async () => {
        await api("POST", `/api/workspaces/${currentWorkspace()}/documents`, form);
        fileInput.value = "";
        await loadDocuments();
    });
});


// --- asking ---

$("ask-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const question = questionBox.value;
    busy("Thinking...", async () => {
        const result = await api("POST", `/api/workspaces/${currentWorkspace()}/ask`, { question });
        showAnswer(result);
    });
});

questionBox.addEventListener("keydown", (event) => {
    // Enter asks; Shift + Enter makes a new line.
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        $("ask-form").requestSubmit();
    }
});

function showAnswer(result) {
    $("answer-text").textContent = result.answer;

    const title = $("sources-title");
    title.textContent = result.related ? "Related passages" : "Sources";
    title.hidden = result.sources.length === 0;

    const sources = $("sources");
    sources.replaceChildren();
    for (const source of result.sources) {
        const card = document.createElement("div");
        card.className = "source-card";

        const where = source.page === null ? source.filename : `${source.filename}, page ${source.page}`;
        const heading = document.createElement("strong");
        heading.textContent = result.related ? where : `[${source.number}] ${where}`;

        const text = document.createElement("p");
        text.textContent = source.text;

        card.append(heading, text);
        sources.append(card);
    }
    $("answer").hidden = false;
}

function hideAnswer() {
    $("answer").hidden = true;
}


// --- start ---

busy("Loading...", () => loadWorkspaces());