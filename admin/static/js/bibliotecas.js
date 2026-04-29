(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);

  const inputArquivo = byId("arquivo");
  const fileName = byId("file-name");
  const fileDrop = inputArquivo ? inputArquivo.closest(".file-drop") : null;
  const formImportacao = byId("formImportacao");

  // =========================================================
  // HELPERS
  // =========================================================
  function extensoesPermitidas() {
    if (!inputArquivo) return [];

    const accept = (inputArquivo.getAttribute("accept") || "").trim();
    if (!accept) return [];

    return accept
      .split(",")
      .map(v => v.trim().toLowerCase())
      .filter(Boolean);
  }

  function arquivoValido(nomeArquivo) {
    const nome = (nomeArquivo || "").toLowerCase();
    const permitidas = extensoesPermitidas();

    if (!permitidas.length) return true;

    return permitidas.some(ext => nome.endsWith(ext));
  }

  function mensagemFormatos() {
    const permitidas = extensoesPermitidas();

    if (!permitidas.length) {
      return "Formato de arquivo inválido.";
    }

    return `O arquivo precisa estar em um destes formatos: ${permitidas.join(", ")}`;
  }

  // =========================================================
  // INPUT FILE
  // =========================================================
  if (inputArquivo && fileName) {
    inputArquivo.addEventListener("change", () => {
      const file = inputArquivo.files && inputArquivo.files[0];
      fileName.textContent = file ? file.name : "Nenhum arquivo selecionado";
    });
  }

  // =========================================================
  // DRAG & DROP
  // =========================================================
  if (fileDrop && inputArquivo) {

    ["dragenter", "dragover"].forEach((eventName) => {
      fileDrop.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        fileDrop.classList.add("dragover");
      });
    });

    ["dragleave", "dragend", "drop"].forEach((eventName) => {
      fileDrop.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        fileDrop.classList.remove("dragover");
      });
    });

    fileDrop.addEventListener("drop", (e) => {
      const files = e.dataTransfer?.files;
      if (!files || !files.length) return;

      inputArquivo.files = files;

      const file = files[0];
      if (fileName) {
        fileName.textContent = file ? file.name : "Nenhum arquivo selecionado";
      }
    });
  }

  // =========================================================
  // SUBMIT VALIDATION
  // =========================================================
  if (formImportacao && inputArquivo) {
    formImportacao.addEventListener("submit", (e) => {
      const file = inputArquivo.files && inputArquivo.files[0];

      if (!file) {
        e.preventDefault();
        alert("Selecione um arquivo antes de importar.");
        return;
      }

      if (!arquivoValido(file.name)) {
        e.preventDefault();
        alert(mensagemFormatos());
        return;
      }
    });
  }

})();