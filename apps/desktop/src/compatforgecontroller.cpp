#include "compatforgecontroller.h"

#include "compatforge.h"

#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QStandardPaths>
#include <QUuid>
#include <QTimer>

namespace {

QString takeString(char *value)
{
    if (value == nullptr) {
        return {};
    }
    const QString result = QString::fromUtf8(value);
    cf_string_free(value);
    return result;
}

QString lastError()
{
    char *value = nullptr;
    if (cf_last_error_json(&value) != CF_STATUS_OK) {
        return QObject::tr("Rust FFI 返回未知错误");
    }
    return takeString(value);
}

QString statusError(uint32_t status)
{
    const QString detail = lastError();
    if (!detail.isEmpty()) {
        return detail;
    }
    return QObject::tr("CompatForge 调用失败（状态码 %1）").arg(status);
}

QString compact(const QJsonObject &object)
{
    return QString::fromUtf8(QJsonDocument(object).toJson(QJsonDocument::Compact));
}

} // namespace

class CompatForgeWorker final : public QObject {
    Q_OBJECT

public:
    explicit CompatForgeWorker(QObject *parent = nullptr)
        : QObject(parent)
    {
    }

    ~CompatForgeWorker() override
    {
        shutdown();
    }

public slots:
    void bootstrap()
    {
        emit busyChanged(true);
        emit runtimeStatus(QObject::tr("正在自动发现 macOS Wine Runtime…"));
        const QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        const QString runtimeStore = QDir(base).filePath(QStringLiteral("runtime-store"));
        const QString storage = QDir(base).filePath(QStringLiteral("storage"));
        QDir().mkpath(runtimeStore);
        QDir().mkpath(storage);

        const QJsonObject request{
            {QStringLiteral("schemaVersion"), QStringLiteral("1")},
            {QStringLiteral("runtimeStoreRoot"), runtimeStore},
            {QStringLiteral("storageRoot"), storage},
        };
        const QByteArray json = QJsonDocument(request).toJson(QJsonDocument::Compact);
        char *receipt = nullptr;
        cf_context_t *context = nullptr;
        const uint32_t status = cf_macos_local_context_create(json.constData(), &context, &receipt);
        if (status != CF_STATUS_OK) {
            if (context != nullptr) {
                cf_context_release(context);
            }
            if (receipt != nullptr) {
                cf_string_free(receipt);
            }
            emit errorChanged(statusError(status));
            emit runtimeStatus(QObject::tr("Runtime bootstrap 失败"));
            emit busyChanged(false);
            return;
        }
        releaseContext();
        m_context = context;
        const QString receiptText = takeString(receipt);
        QJsonParseError parseError{};
        const QJsonDocument parsed = QJsonDocument::fromJson(receiptText.toUtf8(), &parseError);
        if (parseError.error == QJsonParseError::NoError && parsed.isObject()) {
            const QJsonObject value = parsed.object();
            emit runtimeStatus(QObject::tr("Runtime 已就绪：%1 / Pack %2")
                                   .arg(value.value(QStringLiteral("version")).toString(),
                                        value.value(QStringLiteral("packId")).toString()));
        } else {
            emit runtimeStatus(QObject::tr("Runtime 已就绪"));
        }
        emit errorChanged({});
        emit busyChanged(false);
    }

    void prepareExecutable(const QString &path)
    {
        if (m_context == nullptr) {
            emit errorChanged(QObject::tr("请先完成 Runtime bootstrap"));
            return;
        }
        if (path.isEmpty()) {
            emit errorChanged(QObject::tr("没有选择 EXE 文件"));
            return;
        }
        emit busyChanged(true);
        emit runtimeStatus(QObject::tr("正在检查 PE 并生成 LaunchPlan…"));

        const QByteArray pathBytes = path.toUtf8();
        char *inspectionText = nullptr;
        uint32_t status = cf_inspect_executable(pathBytes.constData(), &inspectionText);
        if (status != CF_STATUS_OK) {
            emit errorChanged(statusError(status));
            emit busyChanged(false);
            return;
        }
        const QString inspection = takeString(inspectionText);
        emit inspectionChanged(inspection);
        QJsonParseError parseError{};
        const QJsonDocument report = QJsonDocument::fromJson(inspection.toUtf8(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !report.isObject()) {
            emit errorChanged(QObject::tr("PE inspection 返回了无效 JSON"));
            emit busyChanged(false);
            return;
        }
        const QJsonObject reportObject = report.object();
        const QString architecture = reportObject.value(QStringLiteral("architecture")).toString();
        if (architecture != QStringLiteral("i386") && architecture != QStringLiteral("x86_64")) {
            emit errorChanged(QObject::tr("当前薄壳只接受 i386/x86_64 Windows PE"));
            emit busyChanged(false);
            return;
        }

        const QJsonObject request{
            {QStringLiteral("schemaVersion"), QStringLiteral("1")},
            {QStringLiteral("requestId"), QUuid::createUuid().toString(QUuid::WithoutBraces)},
            {QStringLiteral("bottleId"), QStringLiteral("gui-selected")},
            {QStringLiteral("executable"), QJsonObject{
                {QStringLiteral("path"), path},
                {QStringLiteral("architecture"), architecture},
                {QStringLiteral("mode"), QStringLiteral("immutableArtifact")},
            }},
            {QStringLiteral("constraints"), QJsonObject{
                {QStringLiteral("allowVirtualMachine"), false},
                {QStringLiteral("allowRemote"), false},
                {QStringLiteral("networkPolicy"), QStringLiteral("deny")},
            }},
        };
        const QByteArray requestBytes = QJsonDocument(request).toJson(QJsonDocument::Compact);
        cf_prepared_launch_t *prepared = nullptr;
        status = cf_launch_prepare(m_context, pathBytes.constData(), requestBytes.constData(), &prepared);
        if (status != CF_STATUS_OK) {
            emit errorChanged(statusError(status));
            emit busyChanged(false);
            return;
        }
        releasePrepared();
        m_prepared = prepared;
        char *planText = nullptr;
        status = cf_prepared_launch_plan_get(m_prepared, &planText);
        if (status != CF_STATUS_OK) {
            emit errorChanged(statusError(status));
            releasePrepared();
            emit busyChanged(false);
            return;
        }
        emit planChanged(takeString(planText));
        emit errorChanged({});
        emit canStartChanged(true);
        emit runtimeStatus(QObject::tr("LaunchPlan 已准备，可以启动"));
        emit busyChanged(false);
    }

    void startLaunch()
    {
        if (m_context == nullptr || m_prepared == nullptr || m_launch != nullptr) {
            emit errorChanged(QObject::tr("当前没有可启动的 PreparedLaunch"));
            return;
        }
        emit busyChanged(true);
        cf_launch_t *launch = nullptr;
        const uint32_t status = cf_prepared_launch_start(m_context, m_prepared, &launch);
        if (status != CF_STATUS_OK) {
            emit errorChanged(statusError(status));
            emit busyChanged(false);
            return;
        }
        m_launch = launch;
        emit runtimeStatus(QObject::tr("任务已启动，正在接收 RuntimeEvent"));
        emit busyChanged(false);
        if (m_pollTimer == nullptr) {
            m_pollTimer = new QTimer(this);
            m_pollTimer->setInterval(120);
            connect(m_pollTimer, &QTimer::timeout, this, &CompatForgeWorker::pollEvent);
        }
        m_pollTimer->start();
    }

    void terminateLaunch()
    {
        if (m_launch == nullptr) {
            return;
        }
        const uint32_t status = cf_launch_terminate(m_launch);
        if (status != CF_STATUS_OK) {
            emit errorChanged(statusError(status));
            return;
        }
        emit runtimeStatus(QObject::tr("已请求终止，等待 exited 事件"));
    }

    void shutdown()
    {
        if (m_pollTimer != nullptr) {
            m_pollTimer->stop();
        }
        if (m_launch != nullptr) {
            cf_launch_release(m_launch);
            m_launch = nullptr;
        }
        releasePrepared();
        releaseContext();
    }

private slots:
    void pollEvent()
    {
        if (m_launch == nullptr) {
            return;
        }
        char *eventText = nullptr;
        const uint32_t status = cf_launch_next_event(m_launch, 0, &eventText);
        if (status == CF_STATUS_TIMEOUT) {
            return;
        }
        if (status != CF_STATUS_OK) {
            if (status == CF_STATUS_END_OF_STREAM) {
                emit runtimeStatus(QObject::tr("RuntimeEvent 流已结束"));
            } else {
                emit errorChanged(statusError(status));
            }
            m_pollTimer->stop();
            return;
        }
        const QString event = takeString(eventText);
        emit eventChanged(event);
        QJsonParseError parseError{};
        const QJsonDocument parsed = QJsonDocument::fromJson(event.toUtf8(), &parseError);
        if (parseError.error == QJsonParseError::NoError && parsed.isObject()) {
            const QString kind = parsed.object().value(QStringLiteral("kind")).toString();
            if (kind == QStringLiteral("exited")) {
                m_pollTimer->stop();
                cf_launch_release(m_launch);
                m_launch = nullptr;
                emit canStartChanged(m_prepared != nullptr);
                emit runtimeStatus(QObject::tr("任务已退出"));
            }
        }
    }

signals:
    void runtimeStatus(const QString &value);
    void inspectionChanged(const QString &value);
    void planChanged(const QString &value);
    void eventChanged(const QString &value);
    void errorChanged(const QString &value);
    void busyChanged(bool value);
    void canStartChanged(bool value);

private:
    void releaseContext()
    {
        if (m_context != nullptr) {
            cf_context_release(m_context);
            m_context = nullptr;
        }
    }

    void releasePrepared()
    {
        if (m_prepared != nullptr) {
            cf_prepared_launch_release(m_prepared);
            m_prepared = nullptr;
        }
    }

    cf_context_t *m_context = nullptr;
    cf_prepared_launch_t *m_prepared = nullptr;
    cf_launch_t *m_launch = nullptr;
    QTimer *m_pollTimer = nullptr;
};

CompatForgeController::CompatForgeController(QObject *parent)
    : QObject(parent)
    , m_worker(new CompatForgeWorker)
{
    m_worker->moveToThread(&m_workerThread);
    connect(&m_workerThread, &QThread::finished, m_worker, &QObject::deleteLater);
    connect(m_worker, &CompatForgeWorker::runtimeStatus, this, &CompatForgeController::setRuntimeStatus);
    connect(m_worker, &CompatForgeWorker::inspectionChanged, this, &CompatForgeController::setInspectionSummary);
    connect(m_worker, &CompatForgeWorker::planChanged, this, &CompatForgeController::setPlanSummary);
    connect(m_worker, &CompatForgeWorker::eventChanged, this, &CompatForgeController::appendEvent);
    connect(m_worker, &CompatForgeWorker::errorChanged, this, &CompatForgeController::setError);
    connect(m_worker, &CompatForgeWorker::busyChanged, this, &CompatForgeController::setBusy);
    connect(m_worker, &CompatForgeWorker::canStartChanged, this, &CompatForgeController::setCanStart);
    m_workerThread.start();
}

CompatForgeController::~CompatForgeController()
{
    if (m_workerThread.isRunning()) {
        QMetaObject::invokeMethod(m_worker, &CompatForgeWorker::shutdown, Qt::BlockingQueuedConnection);
        m_workerThread.quit();
        m_workerThread.wait();
    }
}

void CompatForgeController::bootstrap()
{
    QMetaObject::invokeMethod(m_worker, &CompatForgeWorker::bootstrap, Qt::QueuedConnection);
}

void CompatForgeController::prepareExecutable(const QString &path)
{
    QMetaObject::invokeMethod(m_worker, "prepareExecutable", Qt::QueuedConnection, Q_ARG(QString, path));
}

void CompatForgeController::startLaunch()
{
    QMetaObject::invokeMethod(m_worker, &CompatForgeWorker::startLaunch, Qt::QueuedConnection);
}

void CompatForgeController::terminateLaunch()
{
    QMetaObject::invokeMethod(m_worker, &CompatForgeWorker::terminateLaunch, Qt::QueuedConnection);
}

void CompatForgeController::setRuntimeStatus(const QString &value)
{
    if (m_runtimeStatus == value) {
        return;
    }
    m_runtimeStatus = value;
    emit runtimeStatusChanged();
}

void CompatForgeController::setInspectionSummary(const QString &value)
{
    m_inspectionSummary = value;
    emit inspectionSummaryChanged();
}

void CompatForgeController::setPlanSummary(const QString &value)
{
    m_planSummary = value;
    emit planSummaryChanged();
}

void CompatForgeController::appendEvent(const QString &value)
{
    if (!m_eventLog.isEmpty()) {
        m_eventLog.append(QLatin1Char('\n'));
    }
    m_eventLog.append(value);
    emit eventLogChanged();
}

void CompatForgeController::setError(const QString &value)
{
    m_errorDetails = value;
    emit errorDetailsChanged();
}

void CompatForgeController::setBusy(bool value)
{
    if (m_busy == value) {
        return;
    }
    m_busy = value;
    emit busyChanged();
}

void CompatForgeController::setCanStart(bool value)
{
    if (m_canStart == value) {
        return;
    }
    m_canStart = value;
    emit canStartChanged();
}

#include "compatforgecontroller.moc"
