class FhVersions extends HTMLElement {
    constructor(jsonPath = 'versions.json') {
        super();
        this.jsonPath = jsonPath;
        this.currentVersion = null;
        this.versions = [];
        this.render();
    }

    async render() {
        await this.getVersions();

        if (this.versions.length <= 1) {
            this.style.display = 'none';
            return;
        }

        //We add the current version as a non-clickable element (the only one that will be visible when not hovering or clicking)
        const current_version_element = document.createElement('div');
        current_version_element.classList.add('fh-versions-current');
        current_version_element.textContent = this.currentVersion;
        this.appendChild(current_version_element);

        const versions_container = document.createElement('div');
        versions_container.classList.add('fh-versions-versions');

        this.versions.forEach(version => {
            const version_element = document.createElement('div');
            version_element.classList.add('fh-versions-version');
            version_element.textContent = version.version;
            versions_container.appendChild(version_element);
            
            if (version.version !== this.currentVersion) {
                //Redirect to the same page in the selected version. If it doesn't exist, we move to the homepage of the selected version
                version_element.addEventListener('click', async () => {
                    let new_url = window.location.href.replace('/' + this.currentVersion + '/', '/' + version.version + '/');
                    //If the new url doesn't exist, we redirect to the homepage of the selected version
                    if (!await urlExists(new_url)) {
                        new_url = new_url.split('/' + version.version + '/')[0] + '/' + version.version + '/';
                    }
                    window.location.href = new_url;
                });
            } else {
                version_element.classList.add('current');
            }
        });

        this.appendChild(versions_container);

        // Toggle dropdown on click
        this.addEventListener('click', (e) => {
            e.stopPropagation();
            this.classList.toggle('open');
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', () => {
            this.classList.remove('open');
        });
    }

    async getVersions() {
        const [ root_base_path, current_version ] = splitAtLastOccurrence(getBasePath(), '/')
        this.currentVersion = current_version;

        const versions_url = window.location.origin + root_base_path + '/versions.json';
    
        const response = await fetch(versions_url);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        this.versions = await response.json();
    }
}

customElements.define("fh-versions", FhVersions);