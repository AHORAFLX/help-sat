class FlxNavButton extends HTMLElement {
  constructor() {
    super();
  }

  connectedCallback() {
    this.addEventListener("click", ev => {
      const navigation_type = this.getAttribute('type');
      const page_name = this.getAttribute('pagename');
      
      const is_a_process = navigation_type.toLowerCase() === 'execprocess';

      let navigate_fun;
      if (is_a_process) {
        navigate_fun = 'openProcessParams';
      } else if (navigation_type.toLowerCase() === 'viewreport') {
        navigate_fun = 'openReportsParams';
      } else {
        navigate_fun = navigation_type;
      }

      const navigation_json = {
        targetid:"main",
        navigateFun: navigate_fun,
        objectname: this.getAttribute('objectname'),
        objectwhere: this.getAttribute('objectwhere'),
        tablename: this.getAttribute('tablename'),
        tabledescrip: this.getAttribute('tabledescrip'),
        defaults: this.getAttribute('defaults'),
        pagetypeid: this.getAttribute('pagetypeid'),
        helpid: this.getAttribute('helpid'),
        filtersValues:null,
        presetsValues:null,
        //userid:"1",
        pagename: (is_a_process && !page_name) ? 'syspage-processparams-default' : page_name,
        processname: this.getAttribute('processname'),
        reportname: this.getAttribute('reportname'),
        opener:"realMain"
      };
      
      if (isAFlexy() && isOnIframe()) {
          this.navigateInsideFlexy();
          return;
      }

      navigateToFlexy(navigation_json, ev.ctrlKey || ev.metaKey);
    });
  }

  navigateInsideFlexy() {
    //We create a temporary flx-navbutton outside the iframe with every attibute copied and click it
    const btn = window.parent.document.createElement("flx-navbutton");

    for (let i=0; i < this.attributes.length; i++) {
      const attribute = this.attributes[i];
      btn.setAttribute(attribute.name, attribute.value);
    }

    btn.setAttribute("targetid", "sliderightx90%");

    window.parent.document.body.appendChild(btn);
    btn.click();
    window.parent.document.body.removeChild(btn);
  }
}

customElements.define("flx-navbutton", FlxNavButton);