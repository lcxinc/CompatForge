import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.File;
import java.util.Locale;
import javax.imageio.ImageIO;
import javax.swing.UIManager;

public final class SwingFontProbe {
    private static final String SAMPLE = "中文菜单字体 设计 视图 家具";

    public static void main(String[] args) throws Exception {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("file.encoding=" + System.getProperty("file.encoding"));
        System.out.println("sun.jnu.encoding=" + System.getProperty("sun.jnu.encoding"));
        System.out.println("user.language=" + System.getProperty("user.language"));
        System.out.println("user.country=" + System.getProperty("user.country"));
        System.out.println("locale=" + Locale.getDefault());

        probe("Dialog", new Font("Dialog", Font.PLAIN, 22));
        probe("SansSerif", new Font("SansSerif", Font.PLAIN, 22));
        probe("SimSun", new Font("SimSun", Font.PLAIN, 22));
        probe("Microsoft YaHei UI", new Font("Microsoft YaHei UI", Font.PLAIN, 22));
        probe("Hiragino Sans GB", new Font("Hiragino Sans GB", Font.PLAIN, 22));
        probe("Hiragino Sans GB W3", new Font("Hiragino Sans GB W3", Font.PLAIN, 22));
        probe("Hiragino Sans GB W6", new Font("Hiragino Sans GB W6", Font.BOLD, 22));

        Font menuFont = UIManager.getFont("Menu.font");
        Font labelFont = UIManager.getFont("Label.font");
        probe("UIManager.Menu.font", menuFont);
        probe("UIManager.Label.font", labelFont);

        if (args.length > 0) {
            render(new File(args[0]), menuFont != null ? menuFont.deriveFont(22f) : new Font("Dialog", Font.PLAIN, 22));
        }
    }

    private static void probe(String label, Font font) {
        if (font == null) {
            System.out.println(label + "=null");
            return;
        }
        System.out.println(
            label
                + ".family=" + font.getFamily()
                + " name=" + font.getFontName()
                + " canDisplayUpTo=" + font.canDisplayUpTo(SAMPLE)
        );
    }

    private static void render(File output, Font font) throws Exception {
        BufferedImage image = new BufferedImage(760, 160, BufferedImage.TYPE_INT_ARGB);
        Graphics2D graphics = image.createGraphics();
        graphics.setColor(java.awt.Color.WHITE);
        graphics.fillRect(0, 0, image.getWidth(), image.getHeight());
        graphics.setColor(java.awt.Color.BLACK);
        graphics.setFont(font);
        graphics.setRenderingHint(
            RenderingHints.KEY_TEXT_ANTIALIASING,
            RenderingHints.VALUE_TEXT_ANTIALIAS_ON
        );
        graphics.drawString(SAMPLE, 28, 76);
        graphics.drawString(font.getFamily() + " / " + font.getFontName(), 28, 118);
        graphics.dispose();
        ImageIO.write(image, "png", output);
        System.out.println("rendered=" + output.getAbsolutePath());
    }
}
