# Pasos a seguir tras la instalación de SAT by flexygo

Este documento hace referencia a la configuración que debe realizar en el SAT una vez instalado, para poder disponer y gestionar correctamente las imágenes y los documentos.

  

1- Debe cerciorarse de que la base de datos de AHORA ERP a la que hace referencia la instalación cumpla con los siguientes requisitos:

A) Sea una versión 4.4.2300 o superior.

B) Tenga establecido el nivel de compatibilidad con la versión 2016. VER: <[Nivel de compatibilidad](Nivel%20de%20compatibilidad%20de%20la%20base%20de%20datos.md)>

C) Dicha instalación de AHORA ERP debe estar previamente configurada para trabajar con partes. Puede hacerlo desde el asistente de administración de empresas, entrando en el apartado Instalcore

D) Debe tener correctamente establecidas, mediante parámetros de configuración ERP, las rutas de acceso a los documentos y las imágenes del ERP (Asistente de parámetros en ERP o por Tabla CEESI_Configuración).

  

2- Una vez instalado SAT by flexygo en su servidor, acceda a éste con el usuario Admin.

  

3- Habilite las opciones de administrador. Menú - Herramientas - Modo desarrollo

![](https://s3.amazonaws.com/cdn.freshdesk.com/data/helpdesk/attachments/production/2043185286739/original/fnufvy6MgDJpN9IMgXIu0J_acFRPoChAqQ.png?1611222303)

  

4- Abra el menú contextual de la derecha y acceda al área de diseño, seleccione entorno - Parámetros

![](https://s3.amazonaws.com/cdn.freshdesk.com/data/helpdesk/attachments/production/2043185289837/original/MnW_JQGtybEIsxUVRRzRamETmG2iazwYLA.png?1611222834)

  

5- Entre en el apartado Impersonate y establezca las credenciales de un usuario de windows con acceso a las carpetas de imágenes y documentos de AHORA ERP (Parámetros de la tabla CEESI_Configuracion: PATHIMAGENES y PATHFICHEROS)

  

![](https://s3.amazonaws.com/cdn.freshdesk.com/data/helpdesk/attachments/production/2043185290935/original/n5KctHKoW0JRcykknzubTLhV2jAFRF6c-g.png?1611222992)

![](https://s3.amazonaws.com/cdn.freshdesk.com/data/helpdesk/attachments/production/2043185291220/original/9IAu5DOs4iE__sWiztAKjRaHCpdwjLD7PA.png?1611223039)

  

  

6- Si desea geolocalizar los partes y visualizarlos en mapas, debe generar una clave de google y registrarla en la aplicación.

[](https://help.flexygo.com/a/forums/topics/44000316700)<https://help.flexygo.com/a/forums/topics/154000400733>

  

7- Reinicie la aplicación pulsando F5 ó el botón de refresco del navegador.

Una vez realizados estos pasos, ya podrá visualizar las imágenes de los empleados y la aplicación podrá guardar las imágenes en la gestión documental de AHORA ERP