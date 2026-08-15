#include "compatforgecontroller.h"

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QUrl>

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    QCoreApplication::setApplicationName(QStringLiteral("CompatForge"));
    QCoreApplication::setOrganizationDomain(QStringLiteral("compatforge.dev"));
    QQuickStyle::setStyle(QStringLiteral("Basic"));

    QQmlApplicationEngine engine;
    CompatForgeController controller;
    engine.rootContext()->setContextProperty(QStringLiteral("compatForge"), &controller);
    QObject::connect(
        &engine,
        &QQmlApplicationEngine::objectCreationFailed,
        &app,
        [] { QCoreApplication::exit(1); },
        Qt::QueuedConnection);
    engine.load(QUrl(QStringLiteral("qrc:/qt/qml/CompatForge/Desktop/qml/Main.qml")));
    if (engine.rootObjects().isEmpty()) {
        return 1;
    }
    controller.bootstrap();
    return app.exec();
}
