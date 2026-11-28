# Renderiza la geometría de static/mobile/icon.svg con la paleta de Traza bus.
Add-Type -AssemblyName System.Drawing
$iconDirectory = Join-Path $PSScriptRoot '../addons/fleet_rutas/static/mobile'
function New-RoundedPath([single]$x, [single]$y, [single]$width, [single]$height, [single]$radius) {
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $diameter = $radius * 2
    $path.AddArc($x, $y, $diameter, $diameter, 180, 90)
    $path.AddArc(($x + $width - $diameter), $y, $diameter, $diameter, 270, 90)
    $path.AddArc(($x + $width - $diameter), ($y + $height - $diameter), $diameter, $diameter, 0, 90)
    $path.AddArc($x, ($y + $height - $diameter), $diameter, $diameter, 90, 90)
    $path.CloseFigure()
    return ,$path
}
foreach ($size in @(192, 512)) {
    $bitmap = New-Object System.Drawing.Bitmap($size, $size)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.ScaleTransform(($size / 192.0), ($size / 192.0))
    $navy = New-Object System.Drawing.SolidBrush([System.Drawing.ColorTranslator]::FromHtml('#233f62'))
    $purple = New-Object System.Drawing.SolidBrush([System.Drawing.ColorTranslator]::FromHtml('#a77bd8'))
    $white = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    $tile = New-RoundedPath 0 0 192 192 44
    $graphics.FillPath($navy, $tile)
    $body = New-Object System.Drawing.Drawing2D.GraphicsPath
    $body.AddLine(45, 133, 45, 65)
    $body.AddBezier(45, 65, 45, 51.6667, 51.6667, 45, 65, 45)
    $body.AddLine(65, 45, 127, 45)
    $body.AddBezier(127, 45, 140.3333, 45, 147, 51.6667, 147, 65)
    $body.AddLine(147, 65, 147, 133)
    $body.CloseFigure()
    $graphics.FillPath($purple, $body)
    $window = New-RoundedPath 57 62 78 40 8
    $graphics.FillPath($white, $window)
    $skyPen = New-Object System.Drawing.Pen([System.Drawing.ColorTranslator]::FromHtml('#50b2e6'), 9)
    $skyPen.StartCap = $skyPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $graphics.DrawLine($skyPen, 50, 130, 142, 130)
    $graphics.DrawLine($skyPen, 74, 34, 118, 34)
    $graphics.FillEllipse($white, 61, 112, 12, 12)
    $graphics.FillEllipse($white, 119, 112, 12, 12)
    $wheelPen = New-Object System.Drawing.Pen($purple.Color, 12)
    $wheelPen.StartCap = $wheelPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $graphics.DrawLine($wheelPen, 61, 139, 61, 154)
    $graphics.DrawLine($wheelPen, 131, 139, 131, 154)
    $bitmap.Save((Join-Path $iconDirectory "icon-$size.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    foreach ($resource in @($graphics, $bitmap, $navy, $purple, $white, $tile, $body, $window, $skyPen, $wheelPen)) {
        $resource.Dispose()
    }
    Write-Output "Icono actualizado: $size x $size"
}
