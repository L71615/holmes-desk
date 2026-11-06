using System;
using System.Diagnostics;
using System.IO;

// 源码模式下的启动器：编译成带图标的 exe，快捷方式指向它，
// 由它去拉起 pythonw -m holmes_desk（不弹黑框）。
class HolmesDeskLauncher
{
    [STAThread]
    static void Main()
    {
        string dir = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);

        string[] candidates = new string[]
        {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                         @"Programs\Python\Python311\pythonw.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                         @"Programs\Python\Python312\pythonw.exe"),
            @"C:\Python311\pythonw.exe",
            @"C:\Python310\pythonw.exe"
        };

        string py = null;
        foreach (string c in candidates)
        {
            if (File.Exists(c)) { py = c; break; }
        }
        if (py == null) py = "pythonw.exe";

        ProcessStartInfo psi = new ProcessStartInfo(py, "-m holmes_desk");
        psi.WorkingDirectory = dir;
        psi.UseShellExecute = false;
        Process.Start(psi);
    }
}
