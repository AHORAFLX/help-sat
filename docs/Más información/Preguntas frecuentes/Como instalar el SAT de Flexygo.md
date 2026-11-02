# Como instalar el SAT de Flexygo

## Manual de Instalación de AHORA SAT

### Introducción

AHORA SAT es una herramienta desarrollada por AHORA, que utiliza la tecnología de la plataforma Flexygo para generar aplicaciones web dinámicas y configurables. Es complementaria a AHORA ERP y permite gestionar la información relativa a los partes de trabajo, incluso sin conexión.

### Requisitos Previos

  1. Internet Information Services (IIS)

Debe estar instalado, con la característica **WebSocket** habilitada. Si no está instalado, el instalador puede instalarlo.

  2. Microsoft SQL Server

Se requiere SQL Server 2017 o superior. A partir de la versión 10, las bases de datos de la aplicación deben estar en un servidor SQL Server 2017 o posterior. Consulte el manual en la base de conocimiento de AHORA para instrucciones detalladas sobre la configuración del servidor, especialmente la intercalación compatible con AHORA ERP.

  3. .NET Hosting Bundle

El instalador lo instala automáticamente si no lo encuentra.

Puede consultar todos los requisitos en la [ayuda de Flexygo: Requisitos del sistema](https://ayuda.ahora.es/Flexygo/latest/1Deployment/SystemRequirements/).

### Preparativos

  * Asegúrese de tener una base de datos de AHORA ERP versión 4.4.2400 o superior, con el [nivel de compatibilidad](Nivel%20de%20compatibilidad%20de%20la%20base%20de%20datos.md) adecuado.
  * Se recomienda instalar un certificado SSL o TLS en el servidor para garantizar la seguridad de los datos.
  * Habilite los partes de trabajo dentro de AHORA ERP accediendo al asistente de configuración de empresa desde el menú de la aplicación:
    * Menú _Instal Cor_ > Sección _Partes de Taller_.
    * Configure cómo se gestionarán los partes de trabajo según sus necesidades o mantenga la configuración por defecto.

### Instalación del Software

AHORA SAT se instala con el instalador de Flexygo. Puede descargarlo desde la [ayuda de Flexygo](https://ayuda.ahora.es/Flexygo/latest/) o directamente en la siguiente dirección: <https://ayuda.ahora.es/Flexygo/files/flexygoinstallercore.zip>

  1. Ejecución del Instalador

Descomprima el archivo `.zip` descargado y ejecute el instalador como administrador.

  2. Selección de producto

Elija el modo **Despliegue** y seleccione el producto **SAT** en la lista de productos.

  3. Modo de instalación

  * **IIS Básico:** instala el Frontend y el Backend en el mismo servidor y sitio IIS. Indique el nombre del proyecto, el sitio web, el path virtual y el directorio físico.
  * **IIS Avanzado:** permite instalar el Frontend y el Backend en servidores o sitios distintos, instalar IIS o SQL Server si faltan, o instalar una versión concreta del producto.
  * **Docker:** despliega la aplicación en Docker Desktop, para demos, pruebas o desarrollo local. Para producción con Docker, consulte la [ayuda de Flexygo: Docker](https://ayuda.ahora.es/Flexygo/latest/1Deployment/4Docker/).

  4. Finalización

Al terminar, el instalador muestra un resumen y ofrece abrir la aplicación en el navegador.

Tiene el detalle de cada pantalla en la [ayuda de Flexygo: Instalador, modo Despliegue](https://ayuda.ahora.es/Flexygo/latest/1Deployment/1Installer/Deployment/).

### Asistente de Configuración

La primera vez que se accede a la aplicación se abre el asistente de configuración, que guía en cinco pasos:

  1. **Conexión con el backend:** la dirección del frontend y la del backend.
  2. **Base de datos de configuración:** el servidor SQL Server, el usuario, la contraseña y el nombre de la base de datos. Si no existe, el asistente la crea; si es de una versión anterior, la actualiza.
  3. **Proyecto y administrador:** el nombre del proyecto y la contraseña del usuario `admin`.
  4. **Bases de datos de datos:** indique la base de datos de AHORA ERP. Debe existir: el asistente no crea bases de datos del ERP.
  5. **Correo saliente:** la cuenta para enviar emails de bienvenida, recuperar contraseñas y enviar notificaciones. Es opcional y puede configurarse más tarde.

Tiene el detalle de cada paso en la [ayuda de Flexygo: Asistente de configuración](https://ayuda.ahora.es/Flexygo/latest/1Deployment/2ConfigWizard/Configuration/).

### Recomendaciones Post-Instalación

  * Inicie sesión con el usuario `admin` y la contraseña configurada en el asistente para empezar a configurar y utilizar AHORA SAT.
  * Configure las rutas de documentos e imágenes como se indica en [Pasos a seguir tras la instalación de SAT by flexygo](Pasos%20a%20seguir%20tras%20la%20instalaci%C3%B3n%20de%20SAT%20by%20flexygo.md).
  * Navegador Recomendado: Use Google Chrome para un mejor rendimiento.
