# Long-lived Win32 helper for the Operations Center game view.
# Reads one JSON object per line on stdin and writes one JSON object per line on stdout.
# The Electron process is already per-monitor DPI aware; this process must be too or
# SetWindowPos interprets the preview rectangle in virtualized coordinates.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

try {
  Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace Titan {
  public class GameEmbed {
    const long WS_POPUP = 0x80000000L;
    const long WS_CHILD = 0x40000000L;
    const long WS_VISIBLE = 0x10000000L;
    const long WS_CLIPSIBLINGS = 0x04000000L;
    const long WS_CLIPCHILDREN = 0x02000000L;
    const long WS_CAPTION = 0x00C00000L;
    const long WS_THICKFRAME = 0x00040000L;
    const long WS_BORDER = 0x00800000L;
    const long WS_SYSMENU = 0x00080000L;
    const long WS_MINIMIZEBOX = 0x00020000L;
    const long WS_MAXIMIZEBOX = 0x00010000L;
    const long WS_MAXIMIZE = 0x01000000L;
    const long WS_EX_TOPMOST = 0x00000008L;
    const long WS_EX_DLGMODALFRAME = 0x00000001L;
    const long WS_EX_WINDOWEDGE = 0x00000100L;
    const long WS_EX_CLIENTEDGE = 0x00000200L;
    const long WS_EX_STATICEDGE = 0x00020000L;
    const int GWL_STYLE = -16;
    const int GWL_EXSTYLE = -20;
    const int GWLP_HWNDPARENT = -8;
    const uint PLACE_FLAGS = 0x0010 | 0x0040 | 0x0020 | 0x0100;

    [StructLayout(LayoutKind.Sequential)]
    struct RECT { public int Left; public int Top; public int Right; public int Bottom; }

    sealed class Saved {
      public long Style;
      public long ExStyle;
      public long Owner;
      public int Left;
      public int Top;
      public int Width;
      public int Height;
    }

    static readonly Dictionary<string, Saved> saved = new Dictionary<string, Saved>();
    static bool dpiReady;

    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc proc, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hwnd, int cmd);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll")] static extern IntPtr GetParent(IntPtr hwnd);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr hwnd);
    [DllImport("user32.dll")] static extern IntPtr SetFocus(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint from, uint to, bool attach);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] static extern IntPtr GetWindowLongPtrW(IntPtr hwnd, int index);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] static extern IntPtr SetWindowLongPtrW(IntPtr hwnd, int index, IntPtr value);
    [DllImport("user32.dll")] static extern IntPtr SetParent(IntPtr child, IntPtr parent);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "GetWindowTextW")] static extern int GetWindowTextW(IntPtr hwnd, StringBuilder text, int max);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "GetClassNameW")] static extern int GetClassNameW(IntPtr hwnd, StringBuilder text, int max);
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "QueryFullProcessImageNameW")] static extern bool QueryFullProcessImageNameW(IntPtr process, int flags, StringBuilder name, ref int size);
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr hwnd, int attr, out int value, int size);
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    delegate bool EnumProc(IntPtr hwnd, IntPtr lParam);

    public static string Ensure() {
      // PowerShell's process is usually already DPI-unaware by the time this script runs,
      // so the process-wide call fails. The thread context still switches, and that is
      // what SetWindowPos and GetWindowRect consult. Call it on every entry: a later
      // .NET call can reset the thread.
      try { SetThreadDpiAwarenessContext(new IntPtr(-4)); } catch { }
      if (dpiReady) return "ok";
      dpiReady = true;
      try {
        if (!SetProcessDpiAwarenessContext(new IntPtr(-4))) SetProcessDPIAware();
      } catch {
        try { SetProcessDPIAware(); } catch { }
      }
      return "ok";
    }

    public sealed class Found {
      public string Hwnd = "";
      public int Pid;
      public string Title = "";
      public string ClassName = "";
      public string Exe = "";
      public int Width;
      public int Height;
    }

    public sealed class ProbeInfo {
      public bool Alive;
      public string Parent = "0";
      public string Owner = "0";
      public bool Visible;
      public int Width;
      public int Height;
    }

    static IntPtr Parse(string value) {
      if (value == null || value.Length == 0 || value == "0") return IntPtr.Zero;
      long number;
      if (!long.TryParse(value, out number)) return IntPtr.Zero;
      return new IntPtr(number);
    }

    static string Format(IntPtr hwnd) { return hwnd.ToInt64().ToString(); }

    static long StyleOf(IntPtr hwnd) { return GetWindowLongPtrW(hwnd, GWL_STYLE).ToInt64() & 0xFFFFFFFFL; }
    static long ExOf(IntPtr hwnd) { return GetWindowLongPtrW(hwnd, GWL_EXSTYLE).ToInt64() & 0xFFFFFFFFL; }

    static void Remember(IntPtr hwnd) {
      string key = Format(hwnd);
      if (saved.ContainsKey(key)) return;
      RECT rect;
      GetWindowRect(hwnd, out rect);
      Saved snap = new Saved();
      snap.Style = StyleOf(hwnd);
      snap.ExStyle = ExOf(hwnd);
      snap.Owner = GetWindowLongPtrW(hwnd, GWLP_HWNDPARENT).ToInt64();
      snap.Left = rect.Left;
      snap.Top = rect.Top;
      snap.Width = rect.Right - rect.Left;
      snap.Height = rect.Bottom - rect.Top;
      saved[key] = snap;
    }

    static void Prepare(IntPtr hwnd) {
      if (IsIconic(hwnd) || IsZoomed(hwnd)) ShowWindow(hwnd, 4);
    }

    static void Move(IntPtr hwnd, int x, int y, int w, int h) {
      SetWindowPos(hwnd, IntPtr.Zero, x, y, w, h, PLACE_FLAGS);
    }

    static void StripFrame(IntPtr hwnd) {
      long ex = ExOf(hwnd);
      ex &= ~(WS_EX_TOPMOST | WS_EX_DLGMODALFRAME | WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE | WS_EX_STATICEDGE);
      SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new IntPtr(ex));
      int corner = 1;
      try { DwmSetWindowAttribute(hwnd, 33, ref corner, 4); } catch { }
    }

    static bool Cloaked(IntPtr hwnd) {
      int value;
      if (DwmGetWindowAttribute(hwnd, 14, out value, 4) != 0) return false;
      return value != 0;
    }

    static string QueryExe(uint pid) {
      IntPtr handle = OpenProcess(0x1000, false, pid);
      if (handle == IntPtr.Zero) return "";
      try {
        StringBuilder name = new StringBuilder(1024);
        int size = name.Capacity;
        if (!QueryFullProcessImageNameW(handle, 0, name, ref size)) return "";
        return name.ToString();
      } finally {
        CloseHandle(handle);
      }
    }

    public static Found[] Find(string exesCsv, int minWidth, int minHeight) {
      Ensure();
      HashSet<string> wanted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
      if (exesCsv != null) {
        string[] parts = exesCsv.Split(new char[] { ',' });
        for (int i = 0; i < parts.Length; i++) {
          string part = parts[i].Trim();
          if (part.Length > 0) wanted.Add(part);
        }
      }
      List<Found> list = new List<Found>();
      EnumWindows(delegate (IntPtr hwnd, IntPtr lParam) {
        try {
          if (!IsWindowVisible(hwnd) || Cloaked(hwnd)) return true;
          uint pid = 0;
          GetWindowThreadProcessId(hwnd, out pid);
          string exe = QueryExe(pid);
          string file = Path.GetFileName(exe);
          if (!wanted.Contains(file)) return true;
          bool iconic = IsIconic(hwnd);
          RECT rect;
          GetWindowRect(hwnd, out rect);
          int width = rect.Right - rect.Left;
          int height = rect.Bottom - rect.Top;
          if (!iconic && (width < minWidth || height < minHeight)) return true;
          StringBuilder title = new StringBuilder(512);
          GetWindowTextW(hwnd, title, title.Capacity);
          StringBuilder cls = new StringBuilder(256);
          GetClassNameW(hwnd, cls, cls.Capacity);
          Found found = new Found();
          found.Hwnd = Format(hwnd);
          found.Pid = unchecked((int)pid);
          found.Title = title.ToString();
          found.ClassName = cls.ToString();
          found.Exe = exe;
          found.Width = width < 0 ? 0 : width;
          found.Height = height < 0 ? 0 : height;
          list.Add(found);
        } catch { }
        return true;
      }, IntPtr.Zero);
      return list.ToArray();
    }

    public static string Embed(string hwndText, string parentText, int x, int y, int w, int h) {
      Ensure();
      IntPtr hwnd = Parse(hwndText);
      IntPtr parent = Parse(parentText);
      if (!IsWindow(hwnd)) return "window gone";
      if (!IsWindow(parent)) return "Titan window is gone";
      if (w < 2 || h < 2) return "rect too small";
      Remember(hwnd);
      Prepare(hwnd);
      long style = StyleOf(hwnd);
      style &= ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_BORDER | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_MAXIMIZE);
      style |= WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN;
      SetWindowLongPtrW(hwnd, GWL_STYLE, new IntPtr(style));
      SetParent(hwnd, parent);
      if (GetParent(hwnd) != parent) return "SetParent rejected";
      Move(hwnd, x, y, w, h);
      return "";
    }

    public static string Dock(string hwndText, string ownerText, int x, int y, int w, int h) {
      Ensure();
      IntPtr hwnd = Parse(hwndText);
      IntPtr owner = Parse(ownerText);
      if (!IsWindow(hwnd)) return "window gone";
      if (!IsWindow(owner)) return "Titan window is gone";
      if (w < 2 || h < 2) return "rect too small";
      Remember(hwnd);
      Prepare(hwnd);
      SetParent(hwnd, IntPtr.Zero);
      long style = WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN;
      SetWindowLongPtrW(hwnd, GWL_STYLE, new IntPtr(style));
      StripFrame(hwnd);
      SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, owner);
      Move(hwnd, x, y, w, h);
      return "";
    }

    public static string Place(string hwndText, string mode, string anchorText, int x, int y, int w, int h) {
      Ensure();
      IntPtr hwnd = Parse(hwndText);
      if (!IsWindow(hwnd)) return "window gone";
      if (w < 2 || h < 2) return "rect too small";
      if (mode == "dock") {
        long style = StyleOf(hwnd);
        bool popup = (style & WS_POPUP) != 0;
        bool caption = (style & WS_CAPTION) != 0;
        long ownerNow = GetWindowLongPtrW(hwnd, GWLP_HWNDPARENT).ToInt64();
        long want = Parse(anchorText).ToInt64();
        if (!popup || caption || ownerNow != want) return Dock(hwndText, anchorText, x, y, w, h);
      }
      Move(hwnd, x, y, w, h);
      return "";
    }

    public static ProbeInfo Probe(string hwndText) {
      Ensure();
      ProbeInfo info = new ProbeInfo();
      IntPtr hwnd = Parse(hwndText);
      info.Alive = IsWindow(hwnd);
      if (!info.Alive) return info;
      info.Parent = Format(GetParent(hwnd));
      info.Owner = Format(new IntPtr(GetWindowLongPtrW(hwnd, GWLP_HWNDPARENT).ToInt64()));
      info.Visible = IsWindowVisible(hwnd);
      RECT rect;
      GetWindowRect(hwnd, out rect);
      info.Width = rect.Right - rect.Left;
      info.Height = rect.Bottom - rect.Top;
      return info;
    }

    public static string Visible(string hwndText, bool show) {
      Ensure();
      IntPtr hwnd = Parse(hwndText);
      if (!IsWindow(hwnd)) return "window gone";
      ShowWindow(hwnd, show ? 8 : 0);
      return "";
    }

    public static string Focus(string hwndText) {
      Ensure();
      IntPtr hwnd = Parse(hwndText);
      if (!IsWindow(hwnd)) return "window gone";
      ShowWindow(hwnd, 5);
      IntPtr foreground = GetForegroundWindow();
      uint foregroundThread = 0;
      uint targetThread = 0;
      GetWindowThreadProcessId(foreground, out foregroundThread);
      GetWindowThreadProcessId(hwnd, out targetThread);
      uint current = GetCurrentThreadId();
      bool attachedFore = foregroundThread != 0 && foregroundThread != current && AttachThreadInput(current, foregroundThread, true);
      bool attachedTarget = targetThread != 0 && targetThread != current && targetThread != foregroundThread && AttachThreadInput(current, targetThread, true);
      BringWindowToTop(hwnd);
      SetForegroundWindow(hwnd);
      SetFocus(hwnd);
      if (attachedTarget) AttachThreadInput(current, targetThread, false);
      if (attachedFore) AttachThreadInput(current, foregroundThread, false);
      return "";
    }

    public static string Release(string hwndText) {
      Ensure();
      IntPtr hwnd = Parse(hwndText);
      string key = Format(hwnd);
      Saved snap;
      if (!saved.TryGetValue(key, out snap)) {
        if (IsWindow(hwnd)) {
          SetParent(hwnd, IntPtr.Zero);
          SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, IntPtr.Zero);
        }
        return "";
      }
      saved.Remove(key);
      if (!IsWindow(hwnd)) return "";
      SetParent(hwnd, IntPtr.Zero);
      SetWindowLongPtrW(hwnd, GWL_STYLE, new IntPtr(snap.Style));
      SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new IntPtr(snap.ExStyle));
      SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, new IntPtr(snap.Owner));
      int width = snap.Width < 2 ? 1280 : snap.Width;
      int height = snap.Height < 2 ? 720 : snap.Height;
      SetWindowPos(hwnd, IntPtr.Zero, snap.Left, snap.Top, width, height, PLACE_FLAGS);
      return "";
    }

    public static string ReleaseAll() {
      List<string> keys = new List<string>(saved.Keys);
      for (int i = 0; i < keys.Count; i++) Release(keys[i]);
      return "";
    }
  }
}
'@
  [Titan.GameEmbed]::Ensure() | Out-Null
  [Console]::Out.WriteLine('{"ok":true,"op":"ready"}')
  [Console]::Out.Flush()
} catch {
  $msg = $_.Exception.Message.Replace('\', '\\').Replace('"', '\"')
  [Console]::Out.WriteLine('{"ok":false,"op":"ready","error":"' + $msg + '"}')
  [Console]::Out.Flush()
  exit 1
}

function Write-Reply($payload) {
  [Console]::Out.WriteLine(($payload | ConvertTo-Json -Compress -Depth 5))
  [Console]::Out.Flush()
}

# Windows PowerShell 5.1 unwraps a one-element array inside ConvertTo-Json.
function ConvertTo-JsonArray($items) {
  $parts = @()
  foreach ($item in @($items)) {
    $parts += ($item | ConvertTo-Json -Compress -Depth 4)
  }
  if ($parts.Count -eq 0) { return '[]' }
  return '[' + ($parts -join ',') + ']'
}

while ($true) {
  $line = [Console]::In.ReadLine()
  if ($null -eq $line) { break }
  if ($line.Trim().Length -eq 0) { continue }
  $req = $null
  try {
    $req = $line | ConvertFrom-Json
    $op = [string]$req.op
    if ($op -eq 'find') {
      $found = [Titan.GameEmbed]::Find([string]$req.exes, [int]$req.minWidth, [int]$req.minHeight)
      $windows = @()
      if ($null -ne $found) {
        foreach ($row in @($found)) {
          $windows += @{
            hwnd = [string]$row.Hwnd
            pid = [int]$row.Pid
            title = [string]$row.Title
            className = [string]$row.ClassName
            exe = [string]$row.Exe
            width = [int]$row.Width
            height = [int]$row.Height
          }
        }
      }
      $windowsJson = ConvertTo-JsonArray $windows
      [Console]::Out.WriteLine('{"id":' + [int]$req.id + ',"ok":true,"windows":' + $windowsJson + '}')
      [Console]::Out.Flush()
    } elseif ($op -eq 'embed') {
      $err = [Titan.GameEmbed]::Embed([string]$req.hwnd, [string]$req.anchor, [int]$req.x, [int]$req.y, [int]$req.width, [int]$req.height)
      Write-Reply @{ id = $req.id; ok = ($err -eq ''); error = [string]$err }
    } elseif ($op -eq 'dock') {
      $err = [Titan.GameEmbed]::Dock([string]$req.hwnd, [string]$req.anchor, [int]$req.x, [int]$req.y, [int]$req.width, [int]$req.height)
      Write-Reply @{ id = $req.id; ok = ($err -eq ''); error = [string]$err }
    } elseif ($op -eq 'place') {
      $err = [Titan.GameEmbed]::Place([string]$req.hwnd, [string]$req.mode, [string]$req.anchor, [int]$req.x, [int]$req.y, [int]$req.width, [int]$req.height)
      Write-Reply @{ id = $req.id; ok = ($err -eq ''); error = [string]$err }
    } elseif ($op -eq 'probe') {
      $info = [Titan.GameEmbed]::Probe([string]$req.hwnd)
      Write-Reply @{
        id = $req.id
        ok = $true
        alive = [bool]$info.Alive
        parent = [string]$info.Parent
        owner = [string]$info.Owner
        visible = [bool]$info.Visible
        width = [int]$info.Width
        height = [int]$info.Height
      }
    } elseif ($op -eq 'visible') {
      $err = [Titan.GameEmbed]::Visible([string]$req.hwnd, [bool]$req.show)
      Write-Reply @{ id = $req.id; ok = ($err -eq ''); error = [string]$err }
    } elseif ($op -eq 'focus') {
      $err = [Titan.GameEmbed]::Focus([string]$req.hwnd)
      Write-Reply @{ id = $req.id; ok = ($err -eq ''); error = [string]$err }
    } elseif ($op -eq 'release') {
      $err = [Titan.GameEmbed]::Release([string]$req.hwnd)
      Write-Reply @{ id = $req.id; ok = ($err -eq ''); error = [string]$err }
    } elseif ($op -eq 'releaseAll') {
      $err = [Titan.GameEmbed]::ReleaseAll()
      Write-Reply @{ id = $req.id; ok = ($err -eq ''); error = [string]$err }
    } else {
      Write-Reply @{ id = $req.id; ok = $false; error = 'unknown op' }
    }
  } catch {
    $id = 0
    if ($null -ne $req) { $id = $req.id }
    Write-Reply @{ id = $id; ok = $false; error = $_.Exception.Message }
  }
}
