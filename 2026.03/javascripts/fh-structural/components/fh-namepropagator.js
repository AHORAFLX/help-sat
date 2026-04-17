class FHNamePropagator extends HTMLElement {

    constructor() {
      super();

      this.innerHTML = `
        <input part="input" type="text" />
      `;
    }

    connectedCallback() {
        this.placeholder = this.getAttribute("placeholder") || "ProjectName";
        this.selector = this.getAttribute("selector") || "fh-namepropagator-selector";

        this.storage_name = "namepropagator-" + this.selector;

        this.input_element = this.querySelector("input");

        //If local storage has a value, we set it to the input and trigger the propagation
        const stored_value = localStorage.getItem(this.storage_name);
        if (stored_value) {
            this.input_element.value = stored_value;
            this.applyName(stored_value);
        //If not, we set the placeholder
        } else if (this.placeholder) {
            this.input_element.value = this.placeholder;
            this.applyName(this.placeholder);
        }

        //On change, we propagate the name to every element with the selector and store it in local storage (so it persists on reload)
        this.input_element.addEventListener("input", () => {
            const value = this.input_element.value || "";

            this.applyName(value);

            localStorage.setItem(this.storage_name, value);
        });
    }
    
    applyName(value) {
        const elements = document.getElementsByClassName(this.selector);
        for (const element of elements) {
            //If the element is a code block, we need to change the text inside the code block not the full element
            const code_element = element.querySelector("code");
            if (code_element) {
                if (code_element.original_code) {
                    code_element.innerHTML = code_element.original_code;
                } else {
                    code_element.original_code = code_element.innerHTML;
                }

                getElementsWithCertainText(code_element, "fhnamepropagator").forEach((element_to_change) => {
                    element_to_change.textContent = element_to_change.textContent.replace("fhnamepropagator", value);
                });

                continue;
            }

            //If is not a code block, we just change the text content
            element.textContent = value;
        }
    }
}

customElements.define("fh-namepropagator", FHNamePropagator);