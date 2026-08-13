values <- c(1, 2, 3, 4, 5)
result <- data.frame(
  mean = mean(values),
  sd = sd(values),
  chinese = "中文统计"
)

stopifnot(result$mean == 3)
output_path <- file.path(
  "C:/users",
  Sys.getenv("USERNAME"),
  "Temp",
  "macwin-r-statistics.csv"
)
dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
stopifnot(dir.exists(dirname(output_path)))
write.csv(
  result,
  output_path,
  row.names = FALSE,
  fileEncoding = "UTF-8"
)
cat("MACWIN_R_MEAN=", result$mean, "\n", sep = "")
cat("MACWIN_R_OUTPUT=", normalizePath(output_path, winslash = "/"), "\n", sep = "")
