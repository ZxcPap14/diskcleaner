# Scan D: drive - top-level folders size
$target = "D:\"
$skip = @('$Recycle.Bin', 'System Volume Information')

Get-ChildItem $target -Directory | Where-Object { $_.Name -notin $skip } | ForEach-Object {
    $folder = $_
    $size = (Get-ChildItem $folder.FullName -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    $sizeGB = [math]::Round($size / 1GB, 2)
    [PSCustomObject]@{
        Path   = $folder.Name
        SizeGB = $sizeGB
    }
} | Sort-Object SizeGB -Descending | Format-Table -AutoSize -Wrap
