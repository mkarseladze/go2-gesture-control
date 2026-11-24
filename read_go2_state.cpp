#include <chrono>
#include <future>
#include <iostream>
#include <mutex>

#include <unitree/idl/go2/SportModeState_.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: read_go2_state NETWORK_INTERFACE\n";
        return 2;
    }

    using State = unitree_go::msg::dds_::SportModeState_;
    using namespace unitree::robot;
    try {
        ChannelFactory::Instance()->Init(0, argv[1]);
        std::promise<State> first_sample;
        auto sample = first_sample.get_future();
        std::once_flag received;
        ChannelSubscriber<State> subscriber("rt/sportmodestate");
        subscriber.InitChannel([&](const void* message) {
            std::call_once(received, [&] {
                first_sample.set_value(*static_cast<const State*>(message));
            });
        }, 1);
        const bool ready = sample.wait_for(std::chrono::seconds(5)) == std::future_status::ready;
        subscriber.CloseChannel();
        if (!ready) {
            std::cerr << "No rt/sportmodestate samples in 5 seconds.\n";
            return 1;
        }
        const auto state = sample.get();
        const auto& position = state.position();
        const auto& velocity = state.velocity();
        std::cout << "Go2 state received: position = "
                  << position[0] << ", " << position[1] << ", " << position[2]
                  << "; mode=" << static_cast<int>(state.mode())
                  << "; gait=" << static_cast<int>(state.gait_type())
                  << "; vx=" << velocity[0] << " m/s" << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
