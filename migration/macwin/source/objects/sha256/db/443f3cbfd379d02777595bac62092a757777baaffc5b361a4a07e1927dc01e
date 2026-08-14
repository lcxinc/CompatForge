using System;
using System.Collections;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Resources;

class DwsimGdiPlusImageProbe
{
    static int failures;
    static int checkedItems;

    static void CheckImage(string label, Image image)
    {
        checkedItems++;
        try
        {
            string format = image.RawFormat.Guid.ToString();
            Console.WriteLine("PASS\t{0}\t{1}x{2}\t{3}", label, image.Width, image.Height, format);
        }
        catch (Exception ex)
        {
            failures++;
            Console.WriteLine("FAIL\t{0}\t{1}\t{2}", label, ex.GetType().FullName, ex.Message);
        }
    }

    static void CheckImageFile(string path)
    {
        try
        {
            using (Image image = Image.FromFile(path))
            {
                CheckImage("file:" + path, image);
            }
        }
        catch (Exception ex)
        {
            failures++;
            checkedItems++;
            Console.WriteLine("FAIL\tfile:{0}\t{1}\t{2}", path, ex.GetType().FullName, ex.Message);
        }
    }

    static void CheckIcon(string label, Icon icon)
    {
        try
        {
            using (Bitmap bitmap = icon.ToBitmap())
            {
                CheckImage(label + ":icon-bitmap", bitmap);
            }
        }
        catch (Exception ex)
        {
            failures++;
            checkedItems++;
            Console.WriteLine("FAIL\t{0}\t{1}\t{2}", label, ex.GetType().FullName, ex.Message);
        }
    }

    static void CheckResources(string assemblyPath)
    {
        Assembly assembly = Assembly.LoadFrom(assemblyPath);
        foreach (string resourceName in assembly.GetManifestResourceNames())
        {
            if (!resourceName.EndsWith(".resources", StringComparison.OrdinalIgnoreCase))
                continue;

            using (Stream stream = assembly.GetManifestResourceStream(resourceName))
            using (ResourceReader reader = new ResourceReader(stream))
            {
                foreach (DictionaryEntry entry in reader)
                {
                    string label = "resource:" + resourceName + ":" + entry.Key;
                    object value = entry.Value;
                    Image image = value as Image;
                    Icon icon = value as Icon;

                    if (image != null)
                        CheckImage(label, image);
                    else if (icon != null)
                        CheckIcon(label, icon);
                }
            }
        }
    }

    static void Main(string[] args)
    {
        string root = args.Length > 0 ? args[0] : Directory.GetCurrentDirectory();
        string[] extensions = new string[] { "*.png", "*.jpg", "*.jpeg", "*.bmp", "*.ico" };

        foreach (string extension in extensions)
        {
            foreach (string path in Directory.GetFiles(root, extension, SearchOption.AllDirectories))
                CheckImageFile(path);
        }

        CheckResources(Path.Combine(root, "DWSIM.exe"));
        Console.WriteLine("SUMMARY\tchecked={0}\tfailures={1}", checkedItems, failures);
        Environment.Exit(failures == 0 ? 0 : 1);
    }
}
