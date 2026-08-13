#!/usr/bin/env swift

import CoreGraphics
import Foundation

guard CommandLine.arguments.count == 5,
      let fromX = Double(CommandLine.arguments[1]),
      let fromY = Double(CommandLine.arguments[2]),
      let toX = Double(CommandLine.arguments[3]),
      let toY = Double(CommandLine.arguments[4]) else {
    fputs("usage: drag-pointer.swift <from-x> <from-y> <to-x> <to-y>\n", stderr)
    exit(2)
}

let source = CGEventSource(stateID: .hidSystemState)
let start = CGPoint(x: fromX, y: fromY)
let end = CGPoint(x: toX, y: toY)

CGEvent(mouseEventSource: source, mouseType: .mouseMoved, mouseCursorPosition: start, mouseButton: .left)?
    .post(tap: .cghidEventTap)
usleep(150_000)
CGEvent(mouseEventSource: source, mouseType: .leftMouseDown, mouseCursorPosition: start, mouseButton: .left)?
    .post(tap: .cghidEventTap)

for step in 1...20 {
    let fraction = CGFloat(step) / 20
    let point = CGPoint(
        x: start.x + (end.x - start.x) * fraction,
        y: start.y + (end.y - start.y) * fraction
    )
    CGEvent(mouseEventSource: source, mouseType: .leftMouseDragged, mouseCursorPosition: point, mouseButton: .left)?
        .post(tap: .cghidEventTap)
    usleep(20_000)
}

CGEvent(mouseEventSource: source, mouseType: .leftMouseUp, mouseCursorPosition: end, mouseButton: .left)?
    .post(tap: .cghidEventTap)
