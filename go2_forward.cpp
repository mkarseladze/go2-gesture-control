#include <atomic>
#include <cerrno>
#include <exception>
#include <cstdint>
#include <ctime>
#include <iostream>
#include <poll.h>
#include <unistd.h>

#include <unitree/idl/go2/SportModeState_.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>
#include <unitree/robot/go2/sport/sport_client.hpp>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: go2_forward NETWORK_INTERFACE\n";
        return 2;
    }
    try {
        unitree::robot::ChannelFactory::Instance()->Init(0, argv[1]);
        unitree::robot::go2::SportClient client;
        client.SetTimeout(0.15f);
        client.Init();
        using State = unitree_go::msg::dds_::SportModeState_;
        std::atomic<int64_t> last_state_ns{0};
        std::atomic<bool> dancing{false};
        unitree::robot::ChannelSubscriber<State> state("rt/sportmodestate");
        state.InitChannel([&](const void* message) {
            const auto& sample = *static_cast<const State*>(message);
            timespec ts{};
            if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0) {
                dancing.store(sample.progress() > 0.5f);
                last_state_ns.store(ts.tv_sec * INT64_C(1000000000) + ts.tv_nsec);
            }
        }, 1);
        int64_t dance_requested_at = 0;
        bool dance_started = false;
        pollfd input{STDIN_FILENO, POLLIN, 0};
        struct Motion {
            float vx;
            float yaw;
        };
        constexpr Motion motions[] = {
            {0.0f, 0.0f}, {0.35f, 0.0f}, {-0.25f, 0.0f}, {0.0f, 0.45f}, {0.0f, -0.45f}
        };
        int direction = 0;
        int64_t last_move_ns = 0;
        while (true) {
            // Keep the camera heartbeat deadline independent of inference.
            int ready = poll(&input, 1, dance_requested_at ? 50 : (direction != 0 ? 250 : -1));
            if (ready < 0 && errno == EINTR) continue;
            uint64_t commands[512];
            const bool connected = ready > 0 && !(input.revents & (POLLHUP | POLLERR | POLLNVAL));
            ssize_t count = connected ? read(STDIN_FILENO, commands, sizeof commands) : 0;
            timespec now{};
            const bool clock_ok = clock_gettime(CLOCK_MONOTONIC, &now) == 0;
            const int64_t now_ns = now.tv_sec * INT64_C(1000000000) + now.tv_nsec;
            if (dance_requested_at && clock_ok) {
                const auto sample_ns = last_state_ns.load();
                const bool state_fresh = sample_ns >= dance_requested_at &&
                                         now_ns - sample_ns < INT64_C(500000000);
                if (state_fresh && dancing.load()) {
                    if (!dance_started) {
                        std::cout << "Go2 Dance1 started" << std::endl;
                        dance_started = true;
                    }
                } else if (dance_started || now_ns - dance_requested_at > INT64_C(5000000000)) {
                    std::cout << (dance_started ? "Go2 Dance1 ended" : "Go2 Dance1 start unconfirmed")
                              << std::endl;
                    dance_requested_at = 0;
                    dance_started = false;
                }
            }
            const bool valid = count > 0 && count % sizeof(uint64_t) == 0;
            const uint64_t request = valid ? commands[count / sizeof(uint64_t) - 1] : 0;
            const auto sent_ns = static_cast<int64_t>(request >> 4);
            const int requested_direction = request & 15;
            const bool fresh = clock_ok && sent_ns > 0 && now_ns >= sent_ns &&
                               now_ns - sent_ns <= INT64_C(250000000);
            if (fresh && requested_direction >= 1 && requested_direction <= 4) {
                if (direction == requested_direction && now_ns - last_move_ns < INT64_C(50000000)) {
                    continue;
                }
                const auto [vx, yaw] = motions[requested_direction];
                const int result = client.Move(vx, 0.0f, yaw);
                if (result != 0) {
                    std::cerr << "Go2 Move returned " << result << '\n';
                    int stop = client.StopMove();
                    if (stop != 0) std::cerr << "Go2 StopMove returned " << stop << '\n';
                    return 1;
                }
                if (direction != requested_direction) {
                    std::cout << "Go2 accepted Move(" << vx << ", 0, " << yaw << ")" << std::endl;
                }
                direction = requested_direction;
                last_move_ns = now_ns;
                continue;
            }
            if (direction != 0) {
                int result = client.StopMove();
                if (result != 0) {
                    std::cerr << "Go2 StopMove returned " << result << '\n';
                    return 1;
                }
                direction = 0;
            }
            if (fresh && requested_direction >= 5 && requested_direction <= 9) {
                using SportClient = unitree::robot::go2::SportClient;
                struct Action {
                    const char* name;
                    int32_t (SportClient::*call)();
                };
                constexpr Action actions[] = {
                    {"Heart", &SportClient::Heart},
                    {"Sit", &SportClient::Sit},
                    {"StandUp", &SportClient::StandUp},
                    {"Hello", &SportClient::Hello},
                    {"Dance1", &SportClient::Dance1},
                };
                const auto& [name, action] = actions[requested_direction - 5];
                const int result = (client.*action)();
                if (result == 0) {
                    if (requested_direction == 9) dance_requested_at = now_ns;
                    std::cout << "Go2 accepted " << name << "()" << std::endl;
                } else {
                    std::cerr << "Go2 " << name << " returned " << result << '\n';
                }
            }
            if (ready != 0 && count <= 0) return ready < 0 ? 1 : 0;
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
