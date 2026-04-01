# Nivel de compatibilidad de la base de datos

Cada base de datos que creamos con SQL Server tiene una configuración que denominamos nivel de compatibilidad que es nada más que cómo se interpretan los comandos de T-SQL o como se comportan las bases de datos.

No es raro tener bases de datos con un nivel de compatibilidad que no coincida con la versión de SQL Server en la que se ejecutan.

Tener un nivel de compatibilidad antiguo nos priva de numerosas mejoras a nivel de rendimiento y herramientas de programación.

* Para el correcto funcionamiento de SAT by flexygo, es necesario cambiar el nivel de compatibilidad de la base de datos ERP para que puedan funcionar las storeds de sincronización de datos entre los dispositivos móviles, ya que éstas utilizan herramientas de desarrollo presentes en la versión de motor de base de datos 2016.

Pasos a seguir para cambiar el nivel de compatibilidad de una base de datos

Puede cambiar el nivel de compatibilidad ya sea por línea de comandos mediante T-SQL o por desde la interfaz gráfica que proporciona el SSMS de sql server (Management studio de SQL Server).

SSMS:

1- Diríjase a la base de datos en cuestión y haga clic derecho - Propiedades

![](https://s3.amazonaws.com/cdn.freshdesk.com/data/helpdesk/attachments/production/2043125140681/original/qXZJ0MBpAzSsaWsXixe608UytOLmqztuiw.png?1594107433)

2- Seleccione Opciones y en el desplegable de la derecha, seleccione el nivel de compatibilidad que desea. Y por último pulse Aceptar.

![](https://s3.amazonaws.com/cdn.freshdesk.com/data/helpdesk/attachments/production/2043125142116/original/r8XCiXagtuSh8lvykLaLICqIhsaiGAIFjw.png?1594107680)

  

T-SQL
    
    
    /*
    Ver Nivel Compatibilidad
    */
    -- 80 = SQL Server 2000
    -- 90 = SQL Server 2005
    --100 = SQL Server 2008/R2
    --110 = SQL Server 2012
    --120 = SQL Server 2014
    --130 = SQL Server 2016
    

```sql
select name, compatibility_level
    from sys.databases
    WHERE name NOT IN ('master','model','msdb','tempdb')

  

  

CAMBIAR EL NIVEL DE COMPATIBILIDAD DE LA BASE DE DATOS

ALTER DATABASE database_name SET COMPATIBILITY_LEVEL = { 150 | 140 | 130 | 120 | 110 | 100 | 90  }

  

    
    
    --Ejemplo
    ALTER DATABASE AHORA_ERP SET COMPATIBILITY_LEVEL = 130
```