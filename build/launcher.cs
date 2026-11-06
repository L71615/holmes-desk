using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

// 源码模式下的启动器：编译成带图标的 exe，快捷方式指向它，
// 由它去拉起 pythonw -m holmes_desk（不弹黑框）。
// 关键点：把子进程的 stdout/stderr 也写进日志，否则 pythonw 崩了没任何线索。
class HolmesDeskLauncher
{
    static string logPath;
    static readonly object gate = new object();

    [STAThread]
    static void Main()
    {
        string dir = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);
        logPath = Path.Combine(dir, "holmesdesk-launcher.log");

        try
        {
            string py = FindPythonW();
            Log("launch  dir=" + dir + "  python=" + py);

            ProcessStartInfo psi = new ProcessStartInfo(py, "-m holmes_desk");
            psi.WorkingDirectory = dir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            // 不依赖 cwd 与系统编码：显式把程序目录放进 sys.path，并强制 UTF-8。
            string oldPath = Environment.GetEnvironmentVariable("PYTHONPATH");
            psi.EnvironmentVariables["PYTHONPATH"] = string.IsNullOrEmpty(oldPath) ? dir : dir + ";" + oldPath;
            psi.EnvironmentVariables["PYTHONUTF8"] = "1";
            psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

            Process p = new Process();
            p.StartInfo = psi;
            p.OutputDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) Log("  out| " + e.Data); };
            p.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) Log("  err| " + e.Data); };
            p.EnableRaisingEvents = true;
            p.Exited += delegate(object s, EventArgs e)
            {
                Log("exited  code=" + p.ExitCode);
                if (p.ExitCode != 0)
                {
                    MessageBox.Show(
                        "HolmesDesk 启动后立刻退出（代码 " + p.ExitCode + "）。\n\n日志：" + logPath,
                        "HolmesDesk",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                }
            };

            p.Start();
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
            Log("started pid=" + p.Id);
        }
        catch (Exception ex)
        {
            Log("ERROR " + ex);
            MessageBox.Show(
                "启动失败：" + ex.Message + "\n\n详见 " + logPath,
                "HolmesDesk",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    static void Log(string line)
    {
        try
        {
            lock (gate)
            {
                File.AppendAllText(logPath, DateTime.Now.ToString("HH:mm:ss") + "  " + line + "\r\n", Encoding.UTF8);
            }
        }
        catch { }
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
