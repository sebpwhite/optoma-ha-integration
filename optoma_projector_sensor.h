#include "esphome.h"
#include<cmath>

#define DELAY_MS 15000
#define DELAY_MS_LOW_RATE 300000
#define WAIT_FOR_DATA_MS 2000

class OptomaProjectorSensor : public Component, public UARTDevice {
    protected:
        unsigned long lastread;
        unsigned long lastreadlowrate;
        char c;
        int i;
        int sum;
        int power;
        int lchar1, lchar2, lchar3, lchar4;

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
    Sensor *power_sensor = new Sensor();
    Sensor *lamp_hours = new Sensor();
    Sensor *av_input = new Sensor();
    Sensor *feedback = new Sensor();
    Sensor *status_no = new Sensor();

    // constructor
    OptomaProjectorSensor(UARTComponent *parent) : UARTDevice(parent) {}

    void setup() override {
        // This will be called by App.setup()
        lastread = 0;
        lastreadlowrate = 0;
        power=0;
        lchar1=0;
        lchar2=0;
        lchar3=0;
        lchar4=0;
    }
    void loop() override {
        unsigned long now = millis();
        
        while (available()) {
            lchar4 = lchar3;
            lchar3 = lchar2;
            lchar2 = lchar1;
            lchar1 = c;
            c = read();
            //feedback->publish_state(c);
            if (lchar1==79 && lchar2==70 && lchar3==78 && lchar4==73) {
                status_no->publish_state(c-48);
                lastread = now;
                lastreadlowrate = now;
                lchar1=0;
                lchar2=0;
                lchar3=0;
                lchar4=0;
                if ((c-48)==0 || (c-48)==2) {
                    power = 0;
                    power_sensor->publish_state(power);
                }
                if ((c-48)==1) {
                    power = 1;
                    power_sensor->publish_state(power);
                }
            }
        }
        
	    if (now - lastread > DELAY_MS || lastread == 0) {
            //Request Power State
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
                        if (power ==0) {
                            power = 1;
                            power_sensor->publish_state(power);
                        }
                    }
                    if (c==48 && i==2) {
                        if (power ==1) {
                            power = 0;
                            power_sensor->publish_state(power);
                        }
                    }
                i++;
                }
                
            }
            
        }
        if (now - lastreadlowrate > DELAY_MS_LOW_RATE || lastreadlowrate == 0) {
            //Request Lamp Hours
            write(0x7E);
            write(0x30);
            write(0x30);
            write(0x31);
            write(0x30);
            write(0x38);
            write(0x20);
            write(0x31);
            write(0x0D);

		    lastreadlowrate = now;
            i=0;
            sum=0;
            if (data_available()) {
                while (available()) { // Loop while there's data
                    c = read();
                    if (i>=2 && i<=5) {
                        sum = sum + (pow(10,5-i)*(c-48));
                    }
                i++;
                }
                lamp_hours->publish_state(sum);
            }
            if (power==1) {
                //Request Input Selection
                write(0x7E);
                write(0x30);
                write(0x30);
                write(0x31);
                write(0x32);
                write(0x31);
                write(0x20);
                write(0x31);
                write(0x0D);
                i=0;
                if (data_available()) {
                    while (available()) { // Loop while there's data
                        c = read();
                        if (i==2) {
                            av_input->publish_state(c-48);
                        }
                        i++;
                    }
                 }
                
            }
        }
  }
};