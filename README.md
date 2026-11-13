# Dashboard de licencias medicas

## Ejecutar localmente

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\app.py
```

## Fuente de datos

Por defecto, la aplicacion permite cargar manualmente archivos `.xlsx`, `.xls` o `.csv`.

Cada usuario selecciona su propio archivo y el procesamiento se realiza dentro de su sesión. Las bases cargadas no se guardan en GitHub ni en una base central.

## Publicación

El código puede mantenerse en un repositorio público de GitHub y desplegarse en Streamlit Community Cloud. El acceso al dashboard se restringirá mediante Cloudflare Access.
