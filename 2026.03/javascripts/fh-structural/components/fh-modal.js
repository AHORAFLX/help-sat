class FHModal extends HTMLElement {
  constructor() {
    super();
  }

  connectedCallback() {
    this.addEventListener("click", () => {
      if (document.getElementsByClassName('fh-modal-content').length > 0) {
        return;
      }

      const code_element = document.getElementById(this.getAttribute('modal_id'));
      this.presentAsModal(code_element);
    });
  }

  presentAsModal(element) {
    if (!element) {
      console.error("presentAsModal: No element provided");
      return;
    }
    
    //We save position data to restore later
    const original_parent = element.parentNode;
    const original_next_sibling = element.nextSibling;
    
    //We create the backdrop, the title and the content container
    const backdrop = document.createElement("div");
    backdrop.classList.add("fh-modal-backdrop");

    const content_element = document.createElement("div");
    content_element.classList.add("fh-modal-content");

    const title_element = document.createElement("h2");
    title_element.textContent = this.getAttribute('modal_title');

    //We append the modal to the DOM
    content_element.appendChild(title_element);
    content_element.appendChild(element);

    backdrop.appendChild(content_element);
    document.body.appendChild(backdrop);

    // Closes the modal when clicking outside
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) {
        closeModal();
      }
    });

    // Close function
    function closeModal() {
      element.classList.remove("fh-modal-content");

      backdrop.remove();
      if (original_next_sibling) {
        original_parent.insertBefore(element, original_next_sibling);
      } else {
        original_parent.appendChild(element);
      }
    }

    // Return close handler if needed programmatically
    return closeModal;
  }

}

customElements.define("fh-modal", FHModal);