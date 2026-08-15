#include <QtTest>

#include "compatforge.h"
#include "compatforgecontroller.h"

class CompatForgeQtSmoke final : public QObject {
    Q_OBJECT

private slots:
    void apiVersionAndAbiAreStable()
    {
        QVERIFY(cf_api_version() != nullptr);
        QCOMPARE(cf_abi_version(), uint32_t(1));
        QCOMPARE(CF_STATUS_BOOTSTRAP_FAILED, cf_status_t(13));
    }

    void outputHandlesStartNull()
    {
        char *receipt = reinterpret_cast<char *>(uintptr_t(1));
        cf_context_t *context = reinterpret_cast<cf_context_t *>(uintptr_t(1));
        const QByteArray invalid = "{";
        QCOMPARE(
            cf_macos_local_context_create(invalid.constData(), &context, &receipt),
            cf_status_t(CF_STATUS_INVALID_JSON));
        QVERIFY(context == nullptr);
        QVERIFY(receipt == nullptr);
    }

    void bootstrapIsExplicitlyUnavailableOffMacOS()
    {
        char *receipt = reinterpret_cast<char *>(uintptr_t(1));
        cf_context_t *context = reinterpret_cast<cf_context_t *>(uintptr_t(1));
        const QByteArray request =
            "{\"schemaVersion\":\"1\",\"runtimeStoreRoot\":\"/tmp/compatforge-qt-runtime\","
            "\"storageRoot\":\"/tmp/compatforge-qt-storage\"}";
        const cf_status_t status = cf_macos_local_context_create(request.constData(), &context, &receipt);
        if (status == CF_STATUS_OK) {
            QVERIFY(context != nullptr);
            QVERIFY(receipt != nullptr);
            cf_string_free(receipt);
            cf_context_release(context);
        } else {
            QCOMPARE(status, cf_status_t(CF_STATUS_BOOTSTRAP_FAILED));
            QVERIFY(context == nullptr);
            QVERIFY(receipt == nullptr);
        }
    }

    void controllerOwnsWorkerThreadAndCanBeDestroyed()
    {
        CompatForgeController controller;
        QCOMPARE(controller.thread(), QThread::currentThread());
        QVERIFY(!controller.busy());
        QVERIFY(!controller.canStart());
    }
};

QTEST_MAIN(CompatForgeQtSmoke)
#include "tst_compatforgecontroller.moc"
