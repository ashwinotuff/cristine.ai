# actions/reminder.py

import subprocess
import os
import sys
import shutil
import re
import uuid
from datetime import datetime, timedelta
from html import escape as _xml_escape


def reminder(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None
) -> str:
    """
    Sets a timed reminder using Windows Task Scheduler.

    parameters:
        - date    (str) YYYY-MM-DD
        - time    (str) HH:MM
        - message (str)

    Returns a result string - Live API voices it automatically.
    No edge_speak needed.
    """

    date_str = parameters.get("date")
    time_str = parameters.get("time")
    message  = parameters.get("message", "Reminder")

    date_in = str(date_str).strip() if date_str else ""
    time_in = str(time_str).strip() if time_str else ""
    date_provided = bool(date_in)

    if not date_in and not time_in:
        return "I need a time (and optionally a date) to set a reminder."

    try:
        # Accept a couple common time formats so the tool is resilient to model/user formatting.
        date_norm = date_in.replace("/", "-")
        if not date_norm:
            date_norm = datetime.now().strftime("%Y-%m-%d")

        time_raw = time_in
        time_norm = time_raw.upper()
        time_norm = re.sub(r"(?<=\\d)(AM|PM)$", r" \\1", time_norm)  # "3PM" -> "3 PM", "3 PM" unchanged
        time_norm = re.sub(r"^(\\d{1,2})\\s*(AM|PM)$", r"\\1:00 \\2", time_norm)  # "3 PM" -> "3:00 PM"

        # 1) Try absolute parsing first.
        target_dt = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p", "%Y-%m-%d %I %p"):
            try:
                target_dt = datetime.strptime(f"{date_norm} {time_norm}", fmt)
                break
            except ValueError:
                continue

        # 2) Relative parsing fallback ("in a minute", "in 5 minutes", "in 90s", etc.)
        if target_dt is None:
            candidates = [time_raw, f"{date_in} {time_in}".strip()]
            m = None
            for rel_src in candidates:
                rel_src = (rel_src or "").strip()
                if not rel_src:
                    continue
                m = re.match(r"^in\\s+(a|an|\\d+)\\s*(second|seconds|sec|secs|minute|minutes|min|mins|hour|hours|hr|hrs)\\s*$", rel_src, flags=re.IGNORECASE)
                if not m:
                    m = re.match(r"^(a|an|\\d+)\\s*(second|seconds|sec|secs|minute|minutes|min|mins|hour|hours|hr|hrs)\\s*$", rel_src, flags=re.IGNORECASE)
                if not m:
                    m = re.match(r"^in\\s+(\\d+)\\s*([smhd])\\s*$", rel_src, flags=re.IGNORECASE)
                if m:
                    break
            if m:
                qty_raw = m.group(1)
                unit_raw = m.group(2)
                qty = 1 if str(qty_raw).lower() in ("a", "an") else int(qty_raw)
                unit = str(unit_raw).lower()
                seconds = 0
                if unit in ("s", "sec", "secs", "second", "seconds"):
                    seconds = qty
                elif unit in ("m", "min", "mins", "minute", "minutes"):
                    seconds = qty * 60
                elif unit in ("h", "hr", "hrs", "hour", "hours"):
                    seconds = qty * 3600
                elif unit in ("d", "day", "days"):
                    seconds = qty * 86400
                if seconds > 0:
                    target_dt = datetime.now() + timedelta(seconds=seconds)

        if target_dt is None:
            raise ValueError("bad datetime")

        # If the user didn't provide a date (time-only reminder), roll to the next day if needed.
        now_dt = datetime.now()
        if target_dt <= now_dt and not date_provided and time_norm:
            target_dt = target_dt + timedelta(days=1)

        if target_dt <= now_dt:
            return "That time is already in the past."

        task_name = f"CristineReminder_{target_dt.strftime('%Y%m%d_%H%M')}_{uuid.uuid4().hex[:6]}"

        # Keep message safe for XML + generated PowerShell script.
        safe_message = " ".join(str(message).split())
        safe_message = safe_message.replace('"', "").replace("'", "").strip()[:200]
        safe_message_xml = _xml_escape(safe_message)
        # Friendly time string for the popup.
        when_hm = target_dt.strftime("%I:%M %p").lstrip("0")

        temp_dir      = os.environ.get("TEMP", "C:\\Temp")
        os.makedirs(temp_dir, exist_ok=True)
        toast_script = os.path.join(temp_dir, f"{task_name}.ps1")

        # PowerShell popup script (runs via Task Scheduler at the target time).
        # Shows a bottom-right toast window with title + time, independent of Windows notification settings.
        ps_code = r'''
$ErrorActionPreference = "SilentlyContinue"

$TaskName = '__TASK__'
$Title    = '__TITLE__'
$When     = '__WHEN__'

Add-Type -AssemblyName PresentationFramework | Out-Null
Add-Type -AssemblyName PresentationCore      | Out-Null
Add-Type -AssemblyName WindowsBase           | Out-Null
Add-Type -AssemblyName System.Windows.Forms  | Out-Null

try {
  [Console]::Beep(800,200)
  Start-Sleep -Milliseconds 100
  [Console]::Beep(1000,200)
  Start-Sleep -Milliseconds 100
  [Console]::Beep(1200,200)
} catch {}

try {
  $log = Join-Path $env:TEMP 'Cristine_reminder.log'
  Add-Content -LiteralPath $log -Value ("[{0}] fired: {1} @ {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Title, $When)
} catch {}

$wa = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$w = 360
$h = 98
$m = 18

$bg     = [System.Windows.Media.Color]::FromRgb(0x0D,0x1B,0x2E)
$border = [System.Windows.Media.Color]::FromRgb(0x3A,0x5A,0x7E)
$pri    = [System.Windows.Media.Color]::FromRgb(0x4F,0xD1,0xFF)
$sec    = [System.Windows.Media.Color]::FromRgb(0xA6,0x6C,0xFF)
$text   = [System.Windows.Media.Color]::FromRgb(0xCB,0xEF,0xFF)
$text2  = [System.Windows.Media.Color]::FromRgb(0x7F,0xAA,0xC9)

$win = New-Object System.Windows.Window
$win.Width = $w
$win.Height = $h
$win.WindowStyle = 'None'
$win.ResizeMode = 'NoResize'
$win.ShowInTaskbar = $false
$win.Topmost = $true
$win.AllowsTransparency = $true
$win.Background = [System.Windows.Media.Brushes]::Transparent
$win.Left = $wa.Right - $w - $m
$win.Top  = $wa.Bottom - $h - $m
$win.Opacity = 0.0

$outer = New-Object System.Windows.Controls.Border
$outer.Background = New-Object System.Windows.Media.SolidColorBrush($bg)
$outer.BorderBrush = New-Object System.Windows.Media.SolidColorBrush($border)
$outer.BorderThickness = '1'
$outer.CornerRadius = '6'
$outer.Padding = '12,10,12,10'

$stack = New-Object System.Windows.Controls.StackPanel
$stack.Orientation = 'Vertical'

$hdr = New-Object System.Windows.Controls.TextBlock
$hdr.Text = 'REMINDER'
$hdr.Foreground = New-Object System.Windows.Media.SolidColorBrush($sec)
$hdr.FontFamily = 'Consolas'
$hdr.FontSize = 12
$hdr.FontWeight = 'Bold'

$main = New-Object System.Windows.Controls.TextBlock
$main.Text = $Title
$main.Foreground = New-Object System.Windows.Media.SolidColorBrush($pri)
$main.FontFamily = 'Consolas'
$main.FontSize = 16
$main.FontWeight = 'Bold'
$main.TextTrimming = 'CharacterEllipsis'

$t = New-Object System.Windows.Controls.TextBlock
$t.Text = ("AT " + $When)
$t.Foreground = New-Object System.Windows.Media.SolidColorBrush($text)
$t.FontFamily = 'Consolas'
$t.FontSize = 14
$t.FontWeight = 'Bold'

$hint = New-Object System.Windows.Controls.TextBlock
$hint.Text = 'Click to dismiss'
$hint.Foreground = New-Object System.Windows.Media.SolidColorBrush($text2)
$hint.FontFamily = 'Consolas'
$hint.FontSize = 11

$null = $stack.Children.Add($hdr)
$null = $stack.Children.Add($main)
$null = $stack.Children.Add($t)
$null = $stack.Children.Add($hint)
$outer.Child = $stack
$win.Content = $outer

$win.Add_MouseDown({ $win.Close() })

# Fade in quickly so the popup feels intentional (and is easier to notice).
try {
  $fade = New-Object System.Windows.Media.Animation.DoubleAnimation
  $fade.From = 0.0
  $fade.To = 1.0
  $fade.Duration = [System.Windows.Duration]::new([TimeSpan]::FromMilliseconds(220))
  $win.BeginAnimation([System.Windows.Window]::OpacityProperty, $fade)
} catch {
  $win.Opacity = 1.0
}

# Auto-dismiss after 15s, but keep a real WPF message loop running so the window actually renders.
$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromMilliseconds(15000)
$timer.Add_Tick({
  $timer.Stop()
  if ($win.IsVisible) { $win.Close() }
})
$timer.Start()

$null = $win.ShowDialog()

try {
  if ($TaskName) { schtasks /Delete /TN $TaskName /F | Out-Null }
} catch {}

try { Remove-Item -LiteralPath $PSCommandPath -Force } catch {}
'''
        ps_code = (
            ps_code
            .replace("__TASK__", task_name)
            .replace("__TITLE__", safe_message or "Reminder")
            .replace("__WHEN__", when_hm)
        )
        with open(toast_script, "w", encoding="utf-8") as f:
            f.write(ps_code.strip() + "\n")

        # Prefer PowerShell for runtime execution (works even in packaged builds without pythonw).
        ps_exe = shutil.which("powershell.exe") or shutil.which("powershell") or "powershell.exe"
        # Force STA because WPF UI creation can fail silently otherwise.
        ps_args = f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -STA -File "{toast_script}"'

        # Escape command/args for XML text nodes.
        ps_exe_xml = _xml_escape(ps_exe)
        ps_args_xml = _xml_escape(ps_args)

        # Try to fetch current user SID (helps Task Scheduler accept InteractiveToken tasks reliably).
        user_sid_xml = ""
        try:
            who = subprocess.run("whoami /user /fo csv /nh", shell=True, capture_output=True, text=True)
            line = (who.stdout or "").strip().splitlines()[0].strip()
            if line:
                parts = [p.strip().strip('"') for p in line.split(",")]
                if len(parts) >= 2 and parts[1]:
                    user_sid_xml = _xml_escape(parts[1])
        except Exception:
            user_sid_xml = ""

        xml_content = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Cristine Reminder: {safe_message_xml}</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{target_dt.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      {f"<UserId>{user_sid_xml}</UserId>" if user_sid_xml else ""}
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{ps_exe_xml}</Command>
      <Arguments>{ps_args_xml}</Arguments>
    </Exec>
  </Actions>
</Task>'''

        xml_path = os.path.join(temp_dir, f"{task_name}.xml")
        with open(xml_path, "w", encoding="utf-16") as f:
            f.write(xml_content)

        result = subprocess.run(
            f'schtasks /Create /TN "{task_name}" /XML "{xml_path}" /F',
            shell=True, capture_output=True, text=True
        )

        try:
            os.remove(xml_path)
        except Exception:
            pass

        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            print(f"[Reminder] schtasks failed: {err}")
            try:
                os.remove(toast_script)
            except Exception:
                pass
            err_short = " ".join(str(err).split())[:120]
            if player:
                try:
                    player.write_log(f"[reminder] Task Scheduler error: {err_short}", tag="sys")
                except Exception:
                    pass
            return f"I couldn't schedule the reminder (Task Scheduler error: {err_short})."

        if player:
            try:
                player.write_log(
                    f"[reminder] scheduled '{task_name}' for {target_dt.strftime('%Y-%m-%d %H:%M')}",
                    tag="sys",
                )
            except Exception:
                pass

        return f"Reminder set for {target_dt.strftime('%B %d at %I:%M %p')}."

    except ValueError:
        if player:
            try:
                player.write_log("[reminder] Invalid date/time format", tag="sys")
            except Exception:
                pass
        return "I couldn't understand that date or time format."

    except Exception as e:
        msg = f"Something went wrong while scheduling the reminder: {str(e)[:80]}"
        if player:
            try:
                player.write_log(f"[reminder] {msg}", tag="sys")
            except Exception:
                pass
        return msg
