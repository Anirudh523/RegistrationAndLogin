from winotify import Notification, audio

toast = Notification(app_id="NeuralNine Script", title = "Cool", msg = "Hello World", duration = "long")
toast.show()