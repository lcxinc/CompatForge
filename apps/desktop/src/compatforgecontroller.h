#pragma once

#include <QObject>
#include <QString>
#include <QThread>

class CompatForgeWorker;

class CompatForgeController final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString runtimeStatus READ runtimeStatus NOTIFY runtimeStatusChanged)
    Q_PROPERTY(QString inspectionSummary READ inspectionSummary NOTIFY inspectionSummaryChanged)
    Q_PROPERTY(QString planSummary READ planSummary NOTIFY planSummaryChanged)
    Q_PROPERTY(QString eventLog READ eventLog NOTIFY eventLogChanged)
    Q_PROPERTY(QString errorDetails READ errorDetails NOTIFY errorDetailsChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(bool canStart READ canStart NOTIFY canStartChanged)

public:
    explicit CompatForgeController(QObject *parent = nullptr);
    ~CompatForgeController() override;

    QString runtimeStatus() const { return m_runtimeStatus; }
    QString inspectionSummary() const { return m_inspectionSummary; }
    QString planSummary() const { return m_planSummary; }
    QString eventLog() const { return m_eventLog; }
    QString errorDetails() const { return m_errorDetails; }
    bool busy() const { return m_busy; }
    bool canStart() const { return m_canStart; }

    Q_INVOKABLE void bootstrap();
    Q_INVOKABLE void prepareExecutable(const QString &path);
    Q_INVOKABLE void startLaunch();
    Q_INVOKABLE void terminateLaunch();

signals:
    void runtimeStatusChanged();
    void inspectionSummaryChanged();
    void planSummaryChanged();
    void eventLogChanged();
    void errorDetailsChanged();
    void busyChanged();
    void canStartChanged();

private slots:
    void setRuntimeStatus(const QString &value);
    void setInspectionSummary(const QString &value);
    void setPlanSummary(const QString &value);
    void appendEvent(const QString &value);
    void setError(const QString &value);
    void setBusy(bool value);
    void setCanStart(bool value);

private:
    QThread m_workerThread;
    CompatForgeWorker *m_worker = nullptr;
    QString m_runtimeStatus;
    QString m_inspectionSummary;
    QString m_planSummary;
    QString m_eventLog;
    QString m_errorDetails;
    bool m_busy = false;
    bool m_canStart = false;
};
