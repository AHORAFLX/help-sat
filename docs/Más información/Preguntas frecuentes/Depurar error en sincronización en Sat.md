# Depurar error en sincronización en Sat

El objetivo es averiguar cual es la sincronización que queremos depurar (SyncId) y el usuario que está lanzando la misma.

En el ejemplo ejecutaremos las instrucciones sobre la bd del Erp ya que tendremos que ejecutar la stored de sincronización, siendo la base de datos de configuracion del sat la bd -----sat_ic, donde se guardan tanto las cabeceras como las lineas de cada objeto, las imágenes y los documentos enviados.

La stored estandar, a no ser que esté personalizada, es flxsat_offline_partes y las tablas de la base de datos de configuracion que guardan las sincronizaciones son  Offline_Sync, Offline_Sync_Tables para cabecera y datos.

En el actual ejemplo a la hora de ejecutar la stored con los datos de la sincronización utilizaremos el contexto del usuario, ya que es un entorno ERP, y una transacción que descartaremos con el objetivo de ver el error y no afectar a la base de datos.

  

  

\- Note: Executing on configuration database

\-- Getting specific syncronization

\--select * from Offline_Apps

  

\--select * from sat_ic..Offline_Sync order by SyncDate desc

\-- Supongamos que la sincronización a revisar es la E96930AD-7166-4716-AAC8-B01DFEB56CD3 y el usuario es ahora

\-- Y la stored de sincronización es la estandar flxsat_offline_partes 

\--select * from sat_IC..Offline_Sync_Tables where SyncId = 'E96930AD-7166-4716-AAC8-B01DFEB56CD3'

\--select * from offline_sync_tables where syncId='E96930AD-7166-4716-AAC8-B01DFEB56CD3 '

  

\-- Una vez tengamos claro la sincronización y el usuario  

\-- Obtaining variables

```sql
declare @SyncId nvarchar(100)='E96930AD-7166-4716-AAC8-B01DFEB56CD3 '

  

declare @JSONVALUE nvarchar(max)

declare @JSONImages nvarchar(max)

declare @JSONDocuments nvarchar(max)

  

select @JSONVALUE=sat_ic.dbo.fGetJSON(@SyncId,null)

\-- Cargaremos las imagenes y los documentos si los hubiere para la sincronización en la tabla de Offline_Sync_Tables

\--select @JSONImages=sat_ic.dbo.fGetJSON(@SyncId,'flxImages')

\--select @JSONDocuments=sat_ic.dbo.fGetJSON(@SyncId,'flxDocuments')

  

\--Note: Executing stored on Data-- Model database

  

\-- Lo pondremos en una transacción para no afectar a la base de datos y utilizaremos el contextinfo del usuario de la ---´------- sincronización. Deberemos obtener el error en la base de datos, que nos servirá para revisarlo, analizarlo y solventarlo.

begin tran 

exec zSetContextInfo 'ahora'

  

exec flxsat_offline_partes @JSONVALUE, @JSONImages, @JSONDocuments,0 

  

rollback tran
```