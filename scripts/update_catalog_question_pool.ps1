param(
    [string]$WorkbookPath = (Join-Path $PSScriptRoot "..\catalogo_municipios_turisticos_espana_youtube.xlsx")
)

$ErrorActionPreference = "Stop"
$resolvedPath = (Resolve-Path -LiteralPath $WorkbookPath).Path
$workingPath = Join-Path ([System.IO.Path]::GetTempPath()) (
    "youtube-catalog-" + [guid]::NewGuid().ToString("N") + ".xlsx"
)
Copy-Item -LiteralPath $resolvedPath -Destination $workingPath -Force

$excel = $null
$workbook = $null
$saved = $false
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false

    $workbook = $excel.Workbooks.Open($workingPath)
    $placesSheet = $workbook.Worksheets.Item("Lugares")
    $placesTable = $placesSheet.ListObjects.Item("tbl_lugares")

    $columnsToRemove = @(
        "consulta_en_que_hacer",
        "consulta_en_review",
        "consulta_es_opiniones",
        "consulta_es_turismo"
    )
    foreach ($columnName in $columnsToRemove) {
        $columnExists = $false
        for ($column = 1; $column -le $placesTable.ListColumns.Count; $column++) {
            if ($placesTable.ListColumns.Item($column).Name -eq $columnName) {
                $columnExists = $true
                break
            }
        }
        if ($columnExists) {
            $placesTable.ListColumns.Item($columnName).Delete()
        }
    }

    $priorityRange = $placesTable.ListColumns.Item("prioridad").DataBodyRange
    $batchRange = $placesTable.ListColumns.Item("lote_carga").DataBodyRange
    $languageRange = $placesTable.ListColumns.Item("relevance_language").DataBodyRange
    for ($row = 1; $row -le $placesTable.ListRows.Count; $row++) {
        $batch = [int]$batchRange.Cells.Item($row, 1).Value2
        $priorityRange.Cells.Item($row, 1).Value2 = if ($batch -eq 1) { 1 } else { 2 }
        $languageRange.Cells.Item($row, 1).Value2 = "en"
    }

    foreach ($sheet in @($workbook.Worksheets)) {
        if ($sheet.Name -eq "Preguntas") {
            $sheet.Delete()
            break
        }
    }

    $questionsSheet = $workbook.Worksheets.Add($workbook.Worksheets.Item("Listas"))
    $questionsSheet.Name = "Preguntas"
    $questionRows = @()
    $questionRows += ,@("pregunta_id", "nombre", "plantilla_en", "orden", "activa", "aplica_tipologia", "observaciones")
    $questionRows += ,@("Q001", "Opiniones de viaje", "{municipio}, {provincia}, Spain travel review", 1, 1, "TODAS", "Consulta base activa")
    $questionRows += ,@("Q002", "Qué hacer", "things to do in {municipio}, {provincia}, Spain", 2, 1, "TODAS", "Consulta base activa")
    $questionRows += ,@("Q003", "Experiencia turística", "{municipio}, {provincia}, Spain tourist experience", 3, 0, "TODAS", "Disponible para reemplazar una consulta activa")
    $questionRows += ,@("Q004", "Lugares para visitar", "best places to visit in {municipio}, {provincia}, Spain", 4, 0, "TODAS", "Disponible para reemplazar una consulta activa")
    for ($row = 0; $row -lt $questionRows.Count; $row++) {
        for ($column = 0; $column -lt $questionRows[$row].Count; $column++) {
            $value = $questionRows[$row][$column]
            if ($value -is [int]) {
                $questionsSheet.Cells.Item($row + 1, $column + 1).Value2 = [double]$value
            }
            else {
                $questionsSheet.Cells.Item($row + 1, $column + 1).Value2 = [string]$value
            }
        }
    }
    $questionsTable = $questionsSheet.ListObjects.Add(
        1,
        $questionsSheet.Range("A1:G5"),
        $null,
        1
    )
    $questionsTable.Name = "tbl_preguntas"
    $questionsTable.TableStyle = "TableStyleMedium2"
    $questionsSheet.Columns.Item("A").ColumnWidth = 14
    $questionsSheet.Columns.Item("B").ColumnWidth = 24
    $questionsSheet.Columns.Item("C").ColumnWidth = 58
    $questionsSheet.Range("D:F").ColumnWidth = 18
    $questionsSheet.Columns.Item("G").ColumnWidth = 46

    $listsSheet = $workbook.Worksheets.Item("Listas")
    $listsSheet.Cells.Item(2, 2).Value2 = 0.0
    $listsSheet.Cells.Item(3, 2).Value2 = 1.0
    $listsSheet.Cells.Item(4, 2).Value2 = 2.0

    $summarySheet = $workbook.Worksheets.Item("Resumen")
    $summarySheet.Cells.Item(5, 2).Formula = "=COUNTIF(Lugares!O2:O123,1)"
    $summarySheet.Cells.Item(6, 2).Formula = "=COUNTIF(tbl_preguntas[activa],1)"
    $summarySheet.Cells.Item(7, 2).Formula = "=B5*B6"
    $summarySheet.Cells.Item(8, 2).Formula = "=SUMIF(Lugares!O2:O123,1,Lugares!L2:L123)*B6"
    for ($row = 13; $row -le 31; $row++) {
        $summarySheet.Cells.Item($row, 3).Formula = "=COUNTIFS(Lugares!`$E`$2:`$E`$123,A$row,Lugares!`$O`$2:`$O`$123,1)"
    }

    $instructionsSheet = $workbook.Worksheets.Item("Instrucciones")
    $instructionsSheet.Cells.Item(6, 2).Value2 = "Las consultas están en tbl_preguntas. Power Automate combina cada plantilla activa con el municipio y la provincia. Para conservar la cuota diaria, mantenga como máximo dos preguntas globales activas."
    $instructionsSheet.Cells.Item(7, 2).Value2 = "0 = enviado/procesado; 1 = lote actual; 2 = pendiente. Solo debe existir un lote con prioridad 1."
    $instructionsSheet.Cells.Item(8, 2).Value2 = "Al completar el lote actual, sus filas pasan a 0 y el siguiente lote pendiente pasa de 2 a 1."
    $instructionsSheet.Cells.Item(9, 2).Value2 = "Con dos preguntas activas y lotes de 12 o 13 municipios se consumen 24 o 26 llamadas search.list por ejecución."

    $excel.CalculateFullRebuild()
    $workbook.Save()
    $saved = $true
}
finally {
    if ($workbook -ne $null) {
        try { $workbook.Close($false) } catch { }
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook) | Out-Null } catch { }
    }
    if ($excel -ne $null) {
        try { $excel.Quit() } catch { }
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null } catch { }
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

if (-not $saved) {
    throw "Excel no guardó el catálogo temporal."
}
Copy-Item -LiteralPath $workingPath -Destination $resolvedPath -Force
Remove-Item -LiteralPath $workingPath -Force

Write-Output "Catálogo actualizado: $resolvedPath"

