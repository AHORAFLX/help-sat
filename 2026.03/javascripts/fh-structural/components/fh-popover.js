class FHPopover extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.isOpen = false;
    this.handleOutside = this.handleOutside.bind(this);
  }

  connectedCallback() {
    // Ensure mode attribute exists so CSS can see it
    if (!this.hasAttribute("mode")) {
      this.setAttribute("mode", "tooltip");
    }

    const src = this.getAttribute("src");
    const label = this.getAttribute("label") || this.innerHTML;
    const width = this.getAttribute("width") || "200px";
    const mode = this.getAttribute("mode");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          position: relative;
          display: inline-block;
          cursor: pointer;
        }

        .tooltip-container {
          position: absolute;
          bottom: 100%;
          left: 50%;
          transform: translateX(-50%) translateY(-10px);
          opacity: 0;
          visibility: hidden;
          transition: opacity 0.2s, transform 0.2s;
          z-index: 1000;
          background: white;
          padding: 4px;
          border-radius: 8px;
          box-shadow: 0 4px 15px rgba(0,0,0,0.2);
          width: ${width};
          pointer-events: none;
        }

        .tooltip-img {
          width: 100%;
          height: auto;
          display: block;
          border-radius: 4px;
        }

        .tooltip-container::after {
          content: "";
          position: absolute;
          top: 100%;
          left: 50%;
          margin-left: -6px;
          border-width: 6px;
          border-style: solid;
          border-color: white transparent transparent transparent;
        }

        /* Tooltip mode (hover) */
        :host([mode="tooltip"]:hover) .tooltip-container {
          opacity: 1;
          visibility: visible;
          transform: translateX(-50%) translateY(-15px);
        }

        /* Popover mode (click -> [open]) */
        :host([mode="popover"][open]) .tooltip-container {
          opacity: 1;
          visibility: visible;
          pointer-events: auto;
          transform: translateX(-50%) translateY(-15px);
        }
      </style>

      <span class="trigger-text">${label}</span>
      <div class="tooltip-container">
        <img class="tooltip-img" src="${src}" alt="Preview" />
      </div>
    `;

    this.trigger = this.shadowRoot.querySelector(".trigger-text");

    // Only wire click behavior in popover mode
    if (mode === "popover") {
      this.trigger.addEventListener("click", () => this.togglePopover());
      document.addEventListener("click", this.handleOutside);
    }
  }

  disconnectedCallback() {
    document.removeEventListener("click", this.handleOutside);
  }

  togglePopover() {
    this.isOpen = !this.isOpen;
    this.toggleAttribute("open", this.isOpen);
  }

  handleOutside(e) {
    // Close if click happens outside the host
    if (!this.contains(e.target)) {
      this.isOpen = false;
      this.removeAttribute("open");
    }
  }
}

customElements.define("fh-popover", FHPopover);