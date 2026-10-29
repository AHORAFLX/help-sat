class FhCopy extends HTMLElement {
  constructor() {
    super();
  }

  connectedCallback() {
    this.addEventListener("click", () => {
        const text = this.innerText || this.textContent;
        copyToClipboard(text);
    });
  }
}

customElements.define("fh-copy", FhCopy);