/**
 * Template ZIP Download Utility
 */

function downloadTemplateZip() {
    fetch('docs_assets/delete/Template.zip')
        .then(response => {
            if (!response.ok) throw new Error('Template.zip no encontrado');
            return response.blob();
        })
        .then(blob => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'Template.zip';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showDialog('Descarga completada');
        })
        .catch(error => {
            console.error('Error:', error);
            showDialog('❌ Error al descargar: ' + error.message);
        });
}