import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import net.sf.mpxj.Duration;
import net.sf.mpxj.ProjectFile;
import net.sf.mpxj.Resource;
import net.sf.mpxj.Task;
import net.sf.mpxj.TimeUnit;
import net.sf.mpxj.mspdi.MSPDIWriter;
import net.sf.mpxj.reader.UniversalProjectReader;

class ProjectLibreMpxjSmoke {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("usage: project-path result-path");
        }

        ProjectFile project = new ProjectFile();

        Task summary = project.addTask();
        summary.setName("MacWin compatibility project");

        Task planning = summary.addTask();
        planning.setName("\u517c\u5bb9\u6027\u8c03\u8bd5");
        planning.setDuration(Duration.getInstance(2, TimeUnit.DAYS));

        Task validation = summary.addTask();
        validation.setName("ProjectLibre roundtrip");
        validation.setDuration(Duration.getInstance(3.5, TimeUnit.DAYS));

        Resource engineer = project.addResource();
        engineer.setName("\u6d4b\u8bd5\u5de5\u7a0b\u5e08");
        validation.addResourceAssignment(engineer);

        new MSPDIWriter().write(project, args[0]);

        ProjectFile roundtrip = new UniversalProjectReader().read(args[0]);
        if (roundtrip == null) {
            throw new IllegalStateException("ProjectLibre could not read the generated project");
        }

        List<String> taskNames = new ArrayList<>();
        double validationDuration = -1;
        for (Task task : roundtrip.getTasks()) {
            taskNames.add(task.getName());
            if ("ProjectLibre roundtrip".equals(task.getName()) && task.getDuration() != null) {
                validationDuration = task.getDuration().getDuration();
            }
        }

        List<String> resourceNames = new ArrayList<>();
        for (Resource resource : roundtrip.getResources()) {
            if (resource.getName() != null) {
                resourceNames.add(resource.getName());
            }
        }

        if (!taskNames.contains("MacWin compatibility project")
            || !taskNames.contains("\u517c\u5bb9\u6027\u8c03\u8bd5")
            || !taskNames.contains("ProjectLibre roundtrip")) {
            throw new IllegalStateException("task roundtrip mismatch: " + taskNames);
        }
        if (!resourceNames.contains("\u6d4b\u8bd5\u5de5\u7a0b\u5e08")) {
            throw new IllegalStateException("resource roundtrip mismatch: " + resourceNames);
        }
        if (Math.abs(validationDuration - 3.5) > 0.001) {
            throw new IllegalStateException("duration roundtrip mismatch: " + validationDuration);
        }

        List<String> result = List.of(
            "FORMAT=MSPDI",
            "TASKS=" + taskNames.size(),
            "TASK_UNICODE=passed",
            "RESOURCES=" + resourceNames.size(),
            "RESOURCE_UNICODE=passed",
            "DURATION_DAYS=" + validationDuration,
            "ROUNDTRIP=passed"
        );
        Files.write(Path.of(args[1]), result, StandardCharsets.UTF_8);
        System.out.println("PASS projectlibre_mpxj_roundtrip");
    }
}
