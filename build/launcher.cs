using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

// 源码模式下的启动器：编译成带图标的 exe，快捷方式指向它，
// 由它去拉起 pythonw -m holmes_desk（不弹黑框）。
// 任何失败都写进 holmesdesk-launcher.log，并弹窗提示，避免"双击没反应"。
class HolmesDeskLauncher
{
    [STAThread]
    static void Main()
    {
        string dir = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);
        string log = Path.Combine(dir, "holmesdesk-launcher.log");

        try
        {
            string py = FindPythonW();
            File.AppendAllText(log, DateTime.Now.ToString("s") + "  dir=" + dir + "  python=" + py + Environment.NewLine, Encoding.UTF8);

            ProcessStartInfo psi = new ProcessStartInfo(py, "-m holmes_desk");
            psi.WorkingDirectory = dir;
            psi.UseShellExecute = false;
            Process p = Process.Start(psi);
            File.AppendAllText(log, DateTime.Now.ToString("s") + "  started pid=" + p.Id + Environment.NewLine, Encoding.UTF8);
        }
        catch (Exception ex)
        {
            try { File.AppendAllText(log, DateTime.Now.ToString("s") + "  ERROR " + ex + Environment.NewLine, Encoding.UTF8); }
            catch { }
            MessageBox.Show(
                "启动失败：" + ex.Message + "\n\n详见 " + log,
                "HolmesDesk",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    static string FindPythonW()
    {
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string[] candidates = new string[]
        {
            Path.Combine(local, @"Programs\Python\Python313\pythonw.exe"),
            Path.Combine(local, @"Programs\Python\Python312\pythonw.exe"),
            Path.Combine(local, @"Programs\Python\Python311\pythonw.exe"),
            Path.Combine(local, @"Programs\Python\Python310\pythonw.exe"),
            @"C:\Python313\pythonw.exe",
            @"C:\Python312\pythonw.exe",
            @"C:\Python311\pythonw.exe",
            @"C:\Python310\pythonw.exe"
        };
        foreach (string c in candidates)
        {
            if (File.Exists(c)) return c;
        }
        return "pythonw.exe";
    }
}
