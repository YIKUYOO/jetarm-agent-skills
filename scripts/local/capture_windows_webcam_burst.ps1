param(
    [string]$OutputDir,
    [string]$Prefix = "burst",
    [string]$DeviceName = "HD Webcam",
    [int]$Count = 12,
    [int]$IntervalMilliseconds = 250
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Runtime.WindowsRuntime

function Await-Operation {
    param(
        [Parameter(Mandatory = $true)] $AsyncOperation,
        [Parameter(Mandatory = $true)] [Type] $ResultType
    )
    $method = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1 -and
            $_.ReturnType.Name -eq 'Task`1'
        })[0].MakeGenericMethod($ResultType)
    $task = $method.Invoke($null, @($AsyncOperation))
    $task.Wait()
    if ($task.Exception) {
        throw $task.Exception
    }
    return $task.Result
}

function Await-Action {
    param([Parameter(Mandatory = $true)] $AsyncAction)
    $method = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            -not $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1 -and
            $_.ReturnType.Name -eq "Task"
        })[0]
    $task = $method.Invoke($null, @($AsyncAction))
    try {
        $task.Wait()
    }
    catch {
        if ($task.Exception) {
            $task.Exception.Flatten().InnerExceptions | ForEach-Object {
                Write-Error ("WinRT async action failed: {0}: {1}" -f $_.GetType().FullName, $_.Message)
            }
        }
        throw
    }
    if ($task.Exception) {
        $task.Exception.Flatten().InnerExceptions | ForEach-Object {
            Write-Error ("WinRT async action failed: {0}: {1}" -f $_.GetType().FullName, $_.Message)
        }
        throw $task.Exception
    }
}

[Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType = WindowsRuntime] > $null
[Windows.Devices.Enumeration.DeviceClass, Windows.Devices.Enumeration, ContentType = WindowsRuntime] > $null
[Windows.Devices.Enumeration.DeviceInformationCollection, Windows.Devices.Enumeration, ContentType = WindowsRuntime] > $null
[Windows.Media.Capture.MediaCapture, Windows.Media.Capture, ContentType = WindowsRuntime] > $null
[Windows.Media.Capture.MediaCaptureInitializationSettings, Windows.Media.Capture, ContentType = WindowsRuntime] > $null
[Windows.Media.Capture.StreamingCaptureMode, Windows.Media.Capture, ContentType = WindowsRuntime] > $null
[Windows.Media.MediaProperties.ImageEncodingProperties, Windows.Media.MediaProperties, ContentType = WindowsRuntime] > $null
[Windows.Storage.StorageFolder, Windows.Storage, ContentType = WindowsRuntime] > $null
[Windows.Storage.CreationCollisionOption, Windows.Storage, ContentType = WindowsRuntime] > $null

if ($Count -lt 1) {
    throw "Count must be at least 1."
}

$devices = Await-Operation `
    ([Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync([Windows.Devices.Enumeration.DeviceClass]::VideoCapture)) `
    ([Windows.Devices.Enumeration.DeviceInformationCollection])

Write-Output "camera_count=$($devices.Count)"
foreach ($device in $devices) {
    Write-Output "camera=$($device.Name)|$($device.Id)|enabled=$($device.IsEnabled)"
}

$selected = $null
foreach ($device in $devices) {
    if ($device.Name -eq $DeviceName) {
        $selected = $device
        break
    }
}
if ($null -eq $selected -and $devices.Count -gt 0) {
    $selected = $devices[0]
}
if ($null -eq $selected) {
    throw "No Windows video capture device was visible to MediaCapture."
}

$resolvedOutputDir = [System.IO.Path]::GetFullPath($OutputDir)
[System.IO.Directory]::CreateDirectory($resolvedOutputDir) > $null

$folder = Await-Operation `
    ([Windows.Storage.StorageFolder]::GetFolderFromPathAsync($resolvedOutputDir)) `
    ([Windows.Storage.StorageFolder])

$settings = [Windows.Media.Capture.MediaCaptureInitializationSettings]::new()
$settings.VideoDeviceId = $selected.Id
$settings.StreamingCaptureMode = [Windows.Media.Capture.StreamingCaptureMode]::Video

$capture = [Windows.Media.Capture.MediaCapture]::new()
try {
    Await-Action ($capture.InitializeAsync($settings))
    Start-Sleep -Milliseconds 500
    $jpeg = [Windows.Media.MediaProperties.ImageEncodingProperties]::CreateJpeg()
    for ($i = 0; $i -lt $Count; $i++) {
        $name = "{0}_{1:0000}.jpg" -f $Prefix, $i
        $file = Await-Operation `
            ($folder.CreateFileAsync($name, [Windows.Storage.CreationCollisionOption]::ReplaceExisting)) `
            ([Windows.Storage.StorageFile])
        Await-Action ($capture.CapturePhotoToStorageFileAsync($jpeg, $file))
        Write-Output ("saved={0}" -f ([System.IO.Path]::Combine($resolvedOutputDir, $name)))
        if ($i -lt ($Count - 1) -and $IntervalMilliseconds -gt 0) {
            Start-Sleep -Milliseconds $IntervalMilliseconds
        }
    }
}
finally {
    if ($capture -ne $null) {
        $capture.Dispose()
    }
}
