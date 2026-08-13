import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

class DbeaverJdbcSmoke {
    public static void main(String[] args) throws Exception {
        if (args.length != 6) {
            throw new IllegalArgumentException(
                "usage: host port database user result-path expected-driver-version"
            );
        }

        String url = "jdbc:postgresql://" + args[0] + ":" + args[1] + "/" + args[2];
        Properties properties = new Properties();
        properties.setProperty("user", args[3]);
        properties.setProperty("connectTimeout", "5");
        properties.setProperty("socketTimeout", "10");
        Class.forName("org.postgresql.Driver");

        List<String> output = new ArrayList<>();
        try (Connection connection = DriverManager.getConnection(url, properties)) {
            connection.setAutoCommit(false);
            try (Statement statement = connection.createStatement()) {
                statement.execute(
                    "CREATE TEMP TABLE macwin_dbeaver_probe "
                        + "(application text NOT NULL, category text NOT NULL, score numeric NOT NULL)"
                );
            }

            try (PreparedStatement insert = connection.prepareStatement(
                "INSERT INTO macwin_dbeaver_probe(application, category, score) VALUES (?, ?, ?)"
            )) {
                insert.setString(1, "DBeaver JDBC");
                insert.setString(2, "\u4e2d\u6587\u6570\u636e");
                insert.setBigDecimal(3, new java.math.BigDecimal("99.0"));
                insert.addBatch();
                insert.setString(1, "MacWin Java");
                insert.setString(2, "\u6570\u636e\u5e93\u8fde\u63a5");
                insert.setBigDecimal(3, new java.math.BigDecimal("98.0"));
                insert.addBatch();
                int[] updates = insert.executeBatch();
                if (updates.length != 2) {
                    throw new IllegalStateException("unexpected JDBC batch result");
                }
            }

            try (Statement statement = connection.createStatement();
                 ResultSet rows = statement.executeQuery(
                     "SELECT application, category, to_char(score, 'FM9990.0') "
                         + "FROM macwin_dbeaver_probe ORDER BY application"
                 )) {
                while (rows.next()) {
                    output.add("ROW=" + rows.getString(1) + "|" + rows.getString(2) + "|" + rows.getString(3));
                }
            }

            DatabaseMetaData metadata = connection.getMetaData();
            String driverVersion = metadata.getDriverVersion();
            if (!driverVersion.startsWith(args[5])) {
                throw new IllegalStateException("unexpected pgJDBC version: " + driverVersion);
            }
            output.add(0, "DRIVER=" + metadata.getDriverName() + " " + driverVersion);
            output.add(1, "SERVER=" + metadata.getDatabaseProductName() + " " + metadata.getDatabaseProductVersion());
            output.add("UTF8=passed");
            connection.rollback();
        }

        Files.write(Path.of(args[4]), output, StandardCharsets.UTF_8);
    }
}
