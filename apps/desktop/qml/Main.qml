import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: window
    objectName: "compatForgeWindow"
    width: 1120
    height: 760
    minimumWidth: 760
    minimumHeight: 560
    visible: true
    title: qsTr("CompatForge 兼容基线")

    property color panelColor: "#182231"
    property color borderColor: "#2e4258"
    property color accentColor: "#61c6a8"

    FileDialog {
        id: exeDialog
        objectName: "executableFileDialog"
        title: qsTr("选择 Windows EXE")
        nameFilters: [qsTr("Windows 可执行文件 (*.exe)"), qsTr("所有文件 (*)")]
        onAccepted: compatForge.prepareExecutable(selectedFile.toLocalFile())
    }

    background: Rectangle { color: "#0d1420" }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            Label {
                objectName: "titleLabel"
                text: qsTr("CompatForge · Qt 薄壳")
                color: "#eef5ff"
                font.pixelSize: 26
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            Button {
                objectName: "bootstrapButton"
                text: qsTr("重新 Bootstrap")
                enabled: !compatForge.busy
                onClicked: compatForge.bootstrap()
            }
        }

        Label {
            objectName: "runtimeStatusLabel"
            Layout.fillWidth: true
            text: compatForge.runtimeStatus
            color: compatForge.errorDetails.length > 0 ? "#ff9b9b" : accentColor
            wrapMode: Text.Wrap
            Accessible.name: qsTr("Runtime 状态")
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Repeater {
                model: [qsTr("Runtime"), qsTr("Rosetta"), qsTr("WineD3D")]
                delegate: Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 72
                    color: panelColor
                    border.color: borderColor
                    radius: 8
                    Column {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 4
                        Label { text: modelData; color: "#b7c9dd" }
                        Label {
                            text: index === 0 ? qsTr("由 Rust bootstrap") : qsTr("随 Runtime 能力报告")
                            color: "#eef5ff"
                            font.bold: true
                        }
                    }
                }
            }
        }

        GroupBox {
            objectName: "selectionGroup"
            title: qsTr("选择 EXE")
            Layout.fillWidth: true
            RowLayout {
                anchors.fill: parent
                Label {
                    objectName: "selectionHint"
                    text: qsTr("外部 EXE 以 immutableArtifact 检查；Bottle 原位模式由 Core API 门控。")
                    color: "#c6d4e4"
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }
                Button {
                    objectName: "chooseExecutableButton"
                    text: qsTr("选择文件")
                    enabled: !compatForge.busy
                    onClicked: exeDialog.open()
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            GroupBox {
                objectName: "inspectionGroup"
                title: qsTr("Inspection / LaunchPlan")
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent
                    TextArea {
                        objectName: "inspectionText"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        readOnly: true
                        text: compatForge.inspectionSummary
                        placeholderText: qsTr("选择 EXE 后显示 PE inspection")
                        color: "#e4edf8"
                        background: Rectangle { color: "#101a29"; border.color: borderColor }
                    }
                    TextArea {
                        objectName: "planText"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        readOnly: true
                        text: compatForge.planSummary
                        placeholderText: qsTr("Prepared LaunchPlan 摘要")
                        color: "#e4edf8"
                        background: Rectangle { color: "#101a29"; border.color: borderColor }
                    }
                }
            }

            GroupBox {
                objectName: "baselineGroup"
                title: qsTr("GUI 基线应用")
                Layout.preferredWidth: 330
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent
                    Repeater {
                        model: [
                            { id: "gui-7zip", name: qsTr("7-Zip 26.01"), exe: "7zFM.exe" },
                            { id: "gui-sumatrapdf", name: qsTr("SumatraPDF 3.6.1"), exe: "SumatraPDF.exe" },
                            { id: "gui-notepad-plus-plus", name: qsTr("Notepad++ 8.9.6.2"), exe: "notepad++.exe" }
                        ]
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 86
                            color: panelColor
                            border.color: borderColor
                            radius: 7
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                Label { text: modelData.name; color: "#eef5ff"; font.bold: true }
                                Label { text: modelData.id + " · " + modelData.exe; color: "#aabbd0"; font.pixelSize: 12 }
                                Label { text: qsTr("等待 opt-in 真实安装验收"); color: "#e0b87a"; font.pixelSize: 12 }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Button {
                        objectName: "startButton"
                        text: qsTr("启动 PreparedLaunch")
                        Layout.fillWidth: true
                        enabled: compatForge.canStart && !compatForge.busy
                        onClicked: compatForge.startLaunch()
                    }
                    Button {
                        objectName: "terminateButton"
                        text: qsTr("终止活动任务")
                        Layout.fillWidth: true
                        enabled: compatForge.canStart
                        onClicked: compatForge.terminateLaunch()
                    }
                }
            }
        }

        GroupBox {
            objectName: "eventsGroup"
            title: qsTr("RuntimeEvent / 错误详情")
            Layout.fillWidth: true
            Layout.preferredHeight: 130
            RowLayout {
                anchors.fill: parent
                TextArea {
                    objectName: "eventLogText"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    readOnly: true
                    text: compatForge.eventLog
                    color: "#bfe3d8"
                    background: Rectangle { color: "#101a29"; border.color: borderColor }
                }
                TextArea {
                    objectName: "errorDetailsText"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    readOnly: true
                    text: compatForge.errorDetails
                    color: "#ffb1b1"
                    background: Rectangle { color: "#241a24"; border.color: "#76454f" }
                }
            }
        }
    }
}
