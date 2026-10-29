# Versión 10.0

La aplicación estrena una nueva interfaz y mejoras de actualización, seguridad y rendimiento.

## Novedades

### API

- **Se incorpora compatibilidad con MCP en la API de AHORA SAT.** Incluye instrucciones y opciones de configuración para conectar clientes compatibles con MCP. Así, los desarrolladores pueden integrar esos clientes con la API de AHORA SAT.

### Instalación

- **La base de datos de configuración ya no se restaura al reiniciar su contenedor.** Así se evita que el inicio vuelva a modificar la configuración que obliga al administrador a cambiar la contraseña.
- **Puedes desplegar AHORA SAT mediante imágenes Docker, con archivos para la aplicación y sus bases de datos.** La configuración incluye Docker Compose y archivos Docker para la aplicación, la parte de servidor y las bases de datos. También permite excluir contenido innecesario al preparar las imágenes.

## Mejoras

### Aplicación

- **AHORA SAT incorpora la nueva interfaz y las mejoras de actualización, seguridad y rendimiento de Flexygo 10.** La aplicación pasa a ejecutarse sobre Flexygo 10 y .NET 9. También incorpora las mejoras de esta versión en el actualizador, la seguridad y el rendimiento.

### API

- **Consulta descripciones de más propiedades de la API de AHORA SAT.** Las descripciones aportan contexto sobre las propiedades disponibles. Resultan útiles al integrar otras aplicaciones con la API.

### Ayuda

- **Consulta la nueva documentación de AHORA SAT desde la ayuda integrada.** Incluye preguntas frecuentes sobre la aplicación web y la aplicación móvil, además de información sobre instalación, configuración y uso.
