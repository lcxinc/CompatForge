#include "generated.hpp"

#include <cstdint>
#include <iostream>

int main() {
    strucpp::Program_MAIN program;

    for (int cycle = 1; cycle <= 9; ++cycle) {
        program.run();
        if (static_cast<bool>(program.PULSE)) {
            return 10 + cycle;
        }
    }

    program.run();
    if (!static_cast<bool>(program.PULSE)) {
        return 20;
    }
    if (static_cast<std::int32_t>(program.COUNTER) != 0) {
        return 21;
    }

    program.run();
    if (static_cast<bool>(program.PULSE)) {
        return 22;
    }
    if (static_cast<std::int32_t>(program.COUNTER) != 1) {
        return 23;
    }

    std::cout << "MACWIN_OPENPLC_CYCLES=11\n";
    std::cout << "MACWIN_OPENPLC_COUNTER=1\n";
    std::cout << "MACWIN_OPENPLC_PULSE=FALSE\n";
    std::cout << "MACWIN_OPENPLC_SEMANTICS=PASS\n";
    return 0;
}
