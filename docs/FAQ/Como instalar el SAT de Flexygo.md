# Como instalar el SAT de Flexygo

## Manual de Instalación de AHORA SAT

### Introducción

AHORA SAT es una herramienta desarrollada por AHORA  , que utiliza la tecnología de la plataforma Flexygo para generar aplicaciones web dinámicas y configurables. Es complementaria a AHORA ERP y permite gestionar la información relativa a los partes de trabajo, incluso sin conexión.  
  
Puedes acceder al video completo de instalación paso a paso en el siguiente enlace: <https://www.youtube.com/watch?v=T7aTnMRvc7g>  
  

### Requisitos Previos

  1. Internet Information Services (IIS)

Debe estar instalado y correctamente configurado. Consulte el manual en la base de conocimiento de AHORA para más detalles.

  2. Microsoft SQL Server

Se requiere SQL Server versión 2016 o superior. Consulte el manual en la base de conocimiento de AHORA para instrucciones detalladas sobre la configuración del servidor, especialmente la intercalación compatible con AHORA  ERP.

### Descarga e Instalación

  1. Descarga del Instalador

Descargue el archivo instalable desde la siguiente dirección: [](http://nugget.com/barset/upsa/installer.php)[](http://nuget.flexygo.com/setup/satinstaller.zip)<https://docs.flexygo.com/setup/SATInstaller.zip>   
  

  2. Preparativos
     * Asegúrese de tener una base de datos de AHORA  ERP versión 4.4.2000 o superior.
     * Se recomienda instalar un certificado SSL o TLS en el servidor para garantizar la seguridad de los datos.
  3. Configuración Inicial en AHORA ERP
     * Habilite los partes de trabajo dentro de AHORA ERP accediendo al asistente de configuración de empresa desde el menú de la aplicación:
       * Menú _Instal Cor_ > Sección _Partes de Taller_.
       * Configure cómo se gestionarán los partes de trabajo según sus necesidades o mantenga la configuración por defecto.

### Instalación del Software

  1. Extracción del Archivo

El archivo descargado tiene la extensión .zip. Extraiga el contenido utilizando el menú contextual y ejecútelo con permisos de administrador.

  2. Ejecución del Instalador

Abra la carpeta extraída y ejecute _satinstaller.exe_ como administrador.

  3. Pantalla de Bienvenida

Ingrese el nombre del proyecto y la contraseña para el usuario admin. Confirme la contraseña y haga clic en _Next_.

  4. Definición de la Base de Datos de Configuración

El instalador generará una base de datos con el nombre del proyecto seguido del sufijo _config.

  * Configure la instancia de SQL Server (por defecto localhost) y el usuario administrador de SQL Server (por defecto sa).
  * Ingrese la contraseña del usuario administrador y el nombre de la base de datos. Haga clic en _Next_. 

  5. Modelo de Datos de AHORA SAT

Si ya tiene una base de datos de AHORA ERP, asegúrese de que está actualizada a la versión 4.4.2400 o superior.

  * Configure la instancia de SQL Server y el usuario administrador de SQL Server para la base. de datos de AHORA ERP. Ingrese la contraseña del usuario y el nombre de la base de datos. Haga clic en _Next_.
  
  6. Configuración de Documentos e Imágenes

Defina los parámetros para la ruta de documentos e imágenes: _pathFicheros_ , _pathImagenes_ , y pathImagenes_empleados.

  7. Configuración del Servidor de Aplicaciones IIS
     * Configure el nombre del sitio web y el grupo de aplicaciones (_App Pool_) para la aplicación.
     * Establezca el nombre del virtual path y la ruta física de instalación de los archivos de la aplicación. Haga clic en _Next_.
  8. Configuración de la Cuenta de Correo

Ingrese los detalles de una cuenta de correo para enviar emails de bienvenida y validación de usuarios. Este paso no es obligatorio y puede configurarse más tarde en el archivo _web.config_.

  9. Instalación del Producto

Proceda con la instalación. El instalador ofrecerá la opción de instalar el módulo de Crystal Reports si no está instalado previamente.

  10. Finalización

Una vez completada la instalación, el asistente abrirá la aplicación en su navegador predeterminado.

  * Inicie sesión con el usuario administrador y la contraseña configurados.

### Recomendaciones Post-Instalación

  * Navegador Recomendado : Use Google Chrome para un mejor rendimiento.
  * Acceso Inicial : Inicie sesión con las credenciales configuradas durante la instalación para empezar a configurar y utilizar AHORA SAT.