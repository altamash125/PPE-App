(() => {
  // ../ppecon_erp/ppecon_erp/public/js/notification.bundle.js
  function setCookie(name, value, days) {
    let expires = "";
    if (days) {
      const date = new Date();
      date.setTime(date.getTime() + days * 24 * 60 * 60 * 1e3);
      expires = "; expires=" + date.toUTCString();
    }
    document.cookie = name + "=" + (value || "") + expires + "; path=/";
  }
  function getCookie(name) {
    const nameEQ = name + "=";
    const ca = document.cookie.split(";");
    for (let i = 0; i < ca.length; i++) {
      let c = ca[i];
      while (c.charAt(0) === " ")
        c = c.substring(1, c.length);
      if (c.indexOf(nameEQ) === 0)
        return c.substring(nameEQ.length, c.length);
    }
    return null;
  }
  function createQuickChatButton(rootElement) {
    const mainContainer = $("<div></div>");
    const notificationSound = new Audio("/files/pristine-609.mp3");
    const popup = $(`
        <div class="modal fade" id="quick-chat-popup" tabindex="-1" role="dialog" aria-labelledby="exampleModalCenterTitle" aria-hidden="true">
            <div class="modal-dialog" role="document" style="bottom: 60px; position: absolute; right: 20px; max-width: 400px; width: 100%;">
                <div class="modal-content" id="main-quick-chat-container" style="border-radius: 10px; box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.1);">
                    <div class="modal-header" style="background-color: #f1f3f4; color: black; padding: 10px;">
                        <h5 class="modal-title" style="font-weight: bold; color: #343a40;">\u{1F514} Notifications</h5>
                        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                            <span aria-hidden="true">&times;</span>
                        </button>
                    </div>
                    <div class="modal-body" id="notification-list" style="max-height: 400px; overflow-y: auto; padding: 0;">
                        <p style="padding: 15px; text-align: center; color: #777;">No notifications available.</p>
                    </div>
                </div>
            </div>
        </div>
    `);
    const button = $(
      '<button id="quick_chat_button" data-toggle="modal" data-target="#quick-chat-popup" type="button" class="btn btn-primary btn-rounded btn-icon"><i class="fa fa-bell"></i></button>'
    );
    const countElement = $('<span class="count">0</span>');
    countElement.css({
      position: "absolute",
      top: "-5px",
      right: "-5px",
      "background-color": "red",
      color: "white",
      "border-radius": "50%",
      padding: "2px 5px",
      "font-size": "12px",
      "min-width": "20px",
      "text-align": "center"
    });
    button.css({
      position: "fixed",
      bottom: "20px",
      right: "100px",
      "border-radius": "50%",
      width: "50px",
      height: "50px",
      "align-items": "center",
      "justify-content": "center",
      "z-index": "9999",
      "box-shadow": "0px 0px 10px rgba(0, 0, 0, 0.2)",
      "background-color": "#007bff",
      color: "white",
      "font-size": "20px"
    });
    button.append(countElement);
    mainContainer.append(popup);
    mainContainer.append(button);
    $(rootElement).append(mainContainer);
    const mediaStyles = `
        /* Mobile Screens (up to 768px) */
        @media (max-width: 768px) {
            #quick_chat_button {
                bottom: 15px !important;
                right: 30px !important;  /* Adjusted for mobile */
                width: 40px !important;
                height: 40px !important;
                font-size: 18px !important;
            }

            #quick-chat-popup .modal-dialog {
                bottom: 50px !important;
                right: 20px !important;  /* Align the modal with the button */
                max-width: 300px !important;
                width: 100% !important;
            }
        }

        /* Tablet Screens (769px to 1024px) */
        @media (min-width: 769px) and (max-width: 1024px) {
            #quick_chat_button {
                bottom: 20px !important;
                right: 50px !important;  /* Adjusted for tablet */
                width: 45px !important;
                height: 45px !important;
                font-size: 19px !important;
            }

            #quick-chat-popup .modal-dialog {
                bottom: 60px !important;
                right: 35px !important;  /* Align the modal with the button */
                max-width: 350px !important;
                width: 100% !important;
            }
        }

        /* Laptop and Larger Screens (1025px and up) */
        @media (min-width: 1025px) {
            #quick_chat_button {
                bottom: 20px !important;
                right: 100px !important;  /* Adjusted for laptop/desktop */
                width: 50px !important;
                height: 50px !important;
                font-size: 20px !important;
            }

            #quick-chat-popup .modal-dialog {
                bottom: 60px !important;
                right: 20px !important;  /* Align the modal with the button */
                max-width: 400px !important;
                width: 100% !important;
            }
        }
    `;
    $("<style>").text(mediaStyles).appendTo("head");
    let previousNotificationIds = JSON.parse(getCookie("previousNotificationIds")) || [];
    loadNotifications(countElement);
    setInterval(() => loadNotifications(countElement), 1e4);
    addListeners();
    function playNotificationSound() {
      console.log("Playing sound from:", notificationSound.src);
      notificationSound.play().catch(function(error) {
        console.error("Audio playback failed:", error);
      });
    }
    function showToastNotification(message) {
      const toast = $(`
            <div class="toast-notification" style="
                position: fixed;
                top: -50px;
                left: 50%;
                transform: translateX(-50%);
                background-color: #007bff;
                color: white;
                padding: 15px 20px;
                border-radius: 8px;
                box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.1);
                font-size: 16px;
                z-index: 10000;
                opacity: 0;
                transition: all 0.5s ease;
            ">
                ${message}
            </div>
        `);
      $("body").append(toast);
      setTimeout(() => {
        toast.css({
          top: "20px",
          opacity: "1"
        });
      }, 100);
      setTimeout(() => {
        toast.css({
          top: "-50px",
          opacity: "0"
        });
        setTimeout(() => toast.remove(), 500);
      }, 4e3);
    }
    function loadNotifications(countElement2, userTriggered = false) {
      frappe.call({
        method: "ppecon_erp.notification.get_unread_notifications",
        callback: function(response) {
          const notifications = response.message;
          const notificationList = $("#notification-list");
          notificationList.empty();
          if (notifications && notifications.length > 0) {
            const currentNotificationIds = notifications.map(
              (notification) => notification.name
            );
            const newNotifications = currentNotificationIds.filter(
              (id) => !previousNotificationIds.includes(id)
            );
            if (newNotifications.length > 0 && !userTriggered) {
              playNotificationSound();
              showToastNotification(
                "New Notification! Something exciting just happened!"
              );
            }
            previousNotificationIds = currentNotificationIds;
            setCookie(
              "previousNotificationIds",
              JSON.stringify(previousNotificationIds),
              1
            );
            countElement2.text(notifications.length);
            notifications.forEach((notification) => {
              const timeAgo = timeSince(new Date(notification.creation));
              const notificationItem = $(`
                            <div class="notification-item" style="display: flex; align-items: center; padding: 12px; border-bottom: 1px solid #ddd; cursor: pointer;">
                                <div class="notification-content" style="flex-grow: 1; overflow: hidden;">
                                    <strong style="font-size: 14px; color: #007bff;">${notification.subject || "Notification"}</strong>
                                    <p style="font-size: 12px; color: #555; margin: 0;">${notification.email_content || "No content available."}</p>
                                    <span class="notification-time" style="font-size: 11px; color: #888;">${timeAgo}</span>
                                </div>
                            </div>
                        `);
              notificationItem.on("click", async function() {
                await markAsRead(notification.name);
                loadNotifications(countElement2, true);
                window.location.href = `/app/${notification.document_type.toLowerCase()}/${notification.document_name}`;
              });
              notificationList.append(notificationItem);
            });
          } else {
            notificationList.append(
              '<p style="padding: 15px; text-align: center; color: #777;">No notifications available.</p>'
            );
          }
        }
      });
    }
    function timeSince(date) {
      const seconds = Math.floor((new Date() - date) / 1e3);
      let interval = Math.floor(seconds / 31536e3);
      if (interval > 1)
        return interval + " years ago";
      interval = Math.floor(seconds / 2592e3);
      if (interval > 1)
        return interval + " months ago";
      interval = Math.floor(seconds / 86400);
      if (interval > 1)
        return interval + " days ago";
      interval = Math.floor(seconds / 3600);
      if (interval > 1)
        return interval + " hours ago";
      interval = Math.floor(seconds / 60);
      if (interval > 1)
        return interval + " minutes ago";
      return Math.floor(seconds) + " seconds ago";
    }
    function markAsRead(notificationName) {
      return frappe.call({
        method: "ppecon_erp.notification.mark_notification_as_read",
        args: { notification_name: notificationName },
        callback: function(response) {
          loadNotifications($(".count"), true);
        }
      });
    }
    function addListeners() {
      window.addEventListener(
        "quick_chat_child__close_dialog",
        function(data) {
          $("#quick-chat-popup").modal("hide");
        },
        false
      );
    }
  }
  createQuickChatButton(document.querySelector(".main-section"));
})();
//# sourceMappingURL=notification.bundle.KA4OC4L2.js.map
