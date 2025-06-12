"""
NetworkTools - Unified launcher for WiFi and BLE tools
Manages memory efficiently by running one tool at a time
"""

import gc

def show_menu():
    """Show main menu"""
    print("\n" + "=" * 50)
    print("Network Tools for PicoCalc")
    print("=" * 50)
    print("\n1. WiFi Manager")
    print("2. BLE Scanner (Compact)")
    print("3. Fox Hunt Lite (Text)")
    print("4. Fox Hunt Competition")
    print("5. Fox Hunt Pro (Graphics)")
    print("6. Exit")
    
    return input("\nSelect tool (1-6): ").strip()

def main():
    """Main launcher"""
    while True:
        # Clean up memory before showing menu
        gc.collect()
        
        choice = show_menu()
        
        if choice == "1":
            try:
                print("\nLaunching WiFi Manager...")
                import WiFiManager
                WiFiManager.main()
            except Exception as e:
                print(f"Error: {e}")
            finally:
                # Clean up
                try:
                    del WiFiManager
                except:
                    pass
                gc.collect()
                
        elif choice == "2":
            try:
                print("\nLaunching BLE Scanner (Compact)...")
                import ProxiScan_compact
                ProxiScan_compact.main()
            except Exception as e:
                print(f"Error: {e}")
            finally:
                # Clean up
                try:
                    del ProxiScan_compact
                except:
                    pass
                gc.collect()
                
        elif choice == "3":
            try:
                print("\nLaunching Fox Hunt Lite...")
                import FoxHunt_lite
                FoxHunt_lite.main()
            except Exception as e:
                print(f"Error: {e}")
            finally:
                # Clean up
                try:
                    del FoxHunt_lite
                except:
                    pass
                gc.collect()
                
        elif choice == "4":
            try:
                print("\nLaunching Fox Hunt Competition...")
                import FoxHunt_competition
                FoxHunt_competition.main()
            except Exception as e:
                print(f"Error: {e}")
            finally:
                # Clean up
                try:
                    del FoxHunt_competition
                except:
                    pass
                gc.collect()
                
        elif choice == "5":
            try:
                print("\nLaunching Fox Hunt Pro (Graphics)...")
                print("Note: This requires more memory")
                # Use exec to avoid import issues with dots
                exec(open('/sd/py_scripts/ProxiScan_3.0.py').read())
            except Exception as e:
                print(f"Error: {e}")
            finally:
                gc.collect()
                
        elif choice == "6":
            print("Goodbye!")
            break
        else:
            print("Invalid choice")

if __name__ == "__main__":
    main()