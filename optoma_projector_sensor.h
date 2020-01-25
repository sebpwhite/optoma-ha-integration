#include "esphome.h"

#define DELAY_MS 15000
#define WAIT_FOR_DATA_MS 2000

class OptomaProjectorSensor : public Component, public UARTDevice {
    protected:
        unsigned long lastread;
        char c;
        int i;

    // This function borrowed from https://github.com/nldroid/CustomP1UartComponent/blob/master/dsmr_p1_sensor.h    
    bool data_available() {
	// See if there's data available.
	unsigned long currentMillis = millis();
	unsigned long previousMillis = currentMillis; 
  
	while (currentMillis - previousMillis < WAIT_FOR_DATA_MS) { // wait in miliseconds
		currentMillis = millis();
		if (available()) {
			return true;
		}
	}
	return false;  
    }


    public:
    BinarySensor *power_sensor = new BinarySensor();
    // constructor
    OptomaProjectorSensor(UARTComponent *parent) : UARTDevice(parent) {}

    void setup() override {
        // This will be called by App.setup()
        lastread = 0;
    }
    void loop() override {
        unsigned long now = millis();
	
	    if (now - lastread > DELAY_MS || lastread == 0) {
            write(0x7E);
            write(0x30);
            write(0x30);
            write(0x31);
            write(0x32);
            write(0x34);
            write(0x20);
            write(0x31);
            write(0x0D);
		    lastread = now;
            i=0;
            if (data_available()) {
                while (available()) { // Loop while there's data
                    c = read();
                    if (c==49 && i==2) {
                        power_sensor->publish_state(1);
                    }
                    if (c==48 && i==2) {
                        power_sensor->publish_state(0);
                    }
                i++;
                }
            }
            
        }
  }
};