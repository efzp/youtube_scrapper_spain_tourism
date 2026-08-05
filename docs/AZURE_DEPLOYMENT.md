# Despliegue en Azure

La base de datos ya está en **East US**, por lo que conviene crear la Aplicación de funciones y su cuenta de almacenamiento en la misma región.

## 1. Crear la Aplicación de funciones

En el portal de Azure en español:

1. Abre el grupo de recursos del proyecto.
2. Selecciona **Crear** y busca **Aplicación de funciones**.
3. En **Aspectos básicos**, configura:
   - **Publicar**: Código.
   - **Pila del entorno en tiempo de ejecución**: Python.
   - **Versión**: Python 3.11.
   - **Región**: East US.
   - **Plan de hospedaje**: Consumo flexible.
4. Usa una cuenta de almacenamiento del mismo grupo y región, o permite que Azure cree una.
5. Para el piloto, usa 2 GB de memoria y limita el escalado máximo a una instancia.
6. Activa **Application Insights** para conservar los registros de ejecución.
7. Revisa y crea el recurso.

El plan de Consumo flexible permite que el worker siga procesando en segundo plano; `host.json` limita la cola a un trabajo simultáneo y establece un tiempo máximo de una hora.

## 2. Crear la cola

1. Abre la cuenta de almacenamiento usada por la Function App.
2. Ve a **Almacenamiento de datos > Colas**.
3. Selecciona **+ Cola**.
4. Escribe exactamente `youtube-jobs`.

## 3. Activar la identidad administrada

1. Abre la **Aplicación de funciones**.
2. En el menú, abre **Configuración > Identidad**.
3. En **Asignada por el sistema**, cambia **Estado** a **Activado** y guarda.
4. Copia el nombre exacto de la Aplicación de funciones.

## 4. Dar acceso a Azure SQL

Primero, en el recurso **Servidor SQL**, configura un **Administrador de Microsoft Entra** si todavía no existe. Después entra al editor de consultas de la base y ejecuta, reemplazando el marcador por el nombre exacto de la Function App:

```sql
CREATE USER [NOMBRE-DE-LA-FUNCTION-APP] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [NOMBRE-DE-LA-FUNCTION-APP];
ALTER ROLE db_datawriter ADD MEMBER [NOMBRE-DE-LA-FUNCTION-APP];
```

Para el piloto con acceso público al servidor SQL, en **Redes** habilita **Permitir que los servicios y recursos de Azure accedan a este servidor**. La identidad administrada sigue siendo obligatoria para autenticarse. Para producción conviene reemplazar este acceso amplio por red privada.

## 5. Agregar variables de entorno

En la Function App abre **Configuración > Variables de entorno > Configuración de la aplicación** y agrega:

| Nombre | Valor |
|---|---|
| `YOUTUBE_API_KEY` | La clave de YouTube Data API v3 |
| `SQL_CONNECTION_STRING` | `Server=<servidor>.database.windows.net;Database=<base>;Authentication=ActiveDirectoryMSI;Encrypt=yes;TrustServerCertificate=no;` |
| `YOUTUBE_MAX_COMMENTS_PER_VIDEO` | `100` para el piloto |

`AzureWebJobsStorage` y `FUNCTIONS_WORKER_RUNTIME` son creadas normalmente por Azure. Verifica que `FUNCTIONS_WORKER_RUNTIME` tenga el valor `python`.

Para recuperar todos los comentarios disponibles, sin límite de cantidad, deja `YOUTUBE_MAX_COMMENTS_PER_VIDEO` vacío y no envíes `max_comments_per_video` en el POST. Esto no cambia el idioma: siempre se guardan los comentarios en todos los idiomas tal como los entrega YouTube.

## 6. Publicar el código

Desde la raíz del repositorio, con Azure Functions Core Tools y la CLI de Azure autenticada:

```powershell
az login
func azure functionapp publish <NOMBRE-DE-LA-FUNCTION-APP> --python
```

El proyecto ya contiene `function_app.py`, `host.json` y `requirements.txt`. Azure instalará las dependencias durante la publicación.

Si se usa Visual Studio Code, también se puede instalar la extensión **Azure Functions**, iniciar sesión y seleccionar **Implementar en la aplicación de funciones** sobre este directorio.

Después de publicar, la sección **Funciones** debe mostrar:

- `StartYoutubeJob`
- `ProcessYoutubeJob`
- `GetYoutubeJob`

## 7. Probar antes de Power Automate

En `StartYoutubeJob`, selecciona **Obtener la dirección URL de la función**. La URL incluye la clave `code`.

```powershell
$body = @{
    flow_run_id = "prueba-001"
    place_id = "ES-41091"
    municipio = "Sevilla"
    provincia = "Sevilla"
    comunidad_autonoma = "Andalucía"
    consulta_en_review = "Seville Spain travel review"
    consulta_en_que_hacer = "Seville Spain things to do"
    max_results_per_query = 5
    max_comments_per_video = 10
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "<URL-DE-STARTYOUTUBEJOB>" -ContentType "application/json" -Body $body
```

La respuesta debe ser HTTP 202 y contener `run_id`. Luego consulta `GetYoutubeJob` usando su URL y ese identificador. Los estados finales posibles son `COMPLETED`, `PARTIAL` y `FAILED`.

## 8. Conectar Power Automate

En el flujo, después de **Listar las filas presentes en una tabla** y del filtro:

1. Agrega la acción **HTTP**.
2. Método: `POST`.
3. URI: URL de `StartYoutubeJob` con su parámetro `code`.
4. Encabezado `Content-Type`: `application/json`.
5. Construye el cuerpo con la fila actual. Envía solo las consultas inglesas.
6. Usa como `flow_run_id` un identificador estable de la ejecución y de la fila para que un reintento no duplique datos.
7. Guarda el `run_id` devuelto si el flujo necesita comprobar el estado posteriormente.

No es necesario que Power Automate llame directamente a las otras dos funciones: el worker se activa automáticamente desde la cola y la consulta de estado es opcional.
