# Drive a headless Edge (started with --remote-debugging-port=9333) over CDP.
# usage: powershell -File tools\cdp.ps1 <stepsfile>
# steps: wait <ms> | shot <name> | key <code> <key> <vk> | keydown/keyup <code> <key> <vk> | click <x> <y> [button] | mdown/mup <x> <y> [button] | move <x> <y> | eval <js>
param([string]$steps, [int]$port = 9333)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$tabs = (Invoke-WebRequest -UseBasicParsing http://localhost:$port/json).Content | ConvertFrom-Json
$tab = $tabs | Where-Object { $_.type -eq 'page' -and $_.url -like '*localhost:8765*' } | Select-Object -First 1
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ct = [Threading.CancellationToken]::None
$ws.ConnectAsync([Uri]$tab.webSocketDebuggerUrl, $ct).Wait()
$script:id = 0
function Send($method, $params) {
  $script:id++
  $msg = @{ id = $script:id; method = $method; params = $params } | ConvertTo-Json -Depth 8 -Compress
  $bytes = [Text.Encoding]::UTF8.GetBytes($msg)
  $ws.SendAsync([ArraySegment[byte]]::new($bytes), 'Text', $true, $ct).Wait()
  $buf = New-Object byte[] 1048576
  while ($true) {
    $ms = New-Object IO.MemoryStream
    do { $r = $ws.ReceiveAsync([ArraySegment[byte]]::new($buf), $ct).Result; $ms.Write($buf, 0, $r.Count) } while (-not $r.EndOfMessage)
    $txt = [Text.Encoding]::UTF8.GetString($ms.ToArray())
    if ($txt -match ('"id":' + $script:id + '[,}]')) { return $txt }
  }
}
function Btn($b) { if ($b) { $b } else { 'left' } }
foreach ($line in Get-Content $steps) {
  $line = $line.Trim(); if (-not $line -or $line.StartsWith('#')) { continue }
  $p = $line.Split(' ', 2); $cmd = $p[0]; $arg = if ($p.Count -gt 1) { $p[1] } else { '' }; $a = $arg.Split(' ')
  switch ($cmd) {
    'wait' { Start-Sleep -Milliseconds ([int]$arg) }
    'shot' {
      $r = Send 'Page.captureScreenshot' @{ format = 'jpeg'; quality = 88 }
      $m = [regex]::Match($r, '"data":"([^"]+)"'); [IO.File]::WriteAllBytes((Join-Path $root "shots\$arg.jpg"), [Convert]::FromBase64String($m.Groups[1].Value)); Write-Output "shot $arg"
    }
    'eval' { $r = Send 'Runtime.evaluate' @{ expression = $arg; returnByValue = $true; userGesture = $true; awaitPromise = $true }; Write-Output ("eval> " + $r.Substring(0, [Math]::Min(700, $r.Length))) }
    { $_ -in 'key', 'keydown', 'keyup' } {
      $kp = @{ code = $a[0]; key = $a[1]; windowsVirtualKeyCode = [int]$a[2]; nativeVirtualKeyCode = [int]$a[2] }
      if ($cmd -ne 'keyup') { $kp.type = 'rawKeyDown'; [void](Send 'Input.dispatchKeyEvent' $kp) }
      if ($cmd -eq 'key') { Start-Sleep -Milliseconds 60 }
      if ($cmd -ne 'keydown') { $kp.type = 'keyUp'; [void](Send 'Input.dispatchKeyEvent' $kp) }
    }
    { $_ -in 'click', 'mdown', 'mup' } {
      $b = Btn $a[2]; $mp = @{ x = [int]$a[0]; y = [int]$a[1]; button = $b; clickCount = 1 }
      if ($cmd -ne 'mup') { $mp.type = 'mousePressed'; [void](Send 'Input.dispatchMouseEvent' $mp) }
      if ($cmd -eq 'click') { Start-Sleep -Milliseconds 50 }
      if ($cmd -ne 'mdown') { $mp.type = 'mouseReleased'; [void](Send 'Input.dispatchMouseEvent' $mp) }
    }
    'move' { [void](Send 'Input.dispatchMouseEvent' @{ type = 'mouseMoved'; x = [int]$a[0]; y = [int]$a[1] }) }
  }
}
$ws.Dispose()
